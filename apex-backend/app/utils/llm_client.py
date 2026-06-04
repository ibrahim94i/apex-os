"""OpenAI LLM client with rate limiting, 429 backoff, and circuit breaker."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.config import settings
from app.logging_config import logger

T = TypeVar("T", bound=BaseModel)

_rate_lock = asyncio.Lock()
_last_request_at: float = 0.0


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    threshold: int
    recovery_timeout: float = 60.0
    failure_count: int = 0
    state: CircuitState = CircuitState.CLOSED
    last_failure_time: float = 0.0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.threshold:
            self.state = CircuitState.OPEN
            logger.warning("llm_circuit_breaker_open", failures=self.failure_count)

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True


@dataclass
class LLMResponse:
    content: str
    model: str
    latency_ms: float
    usage: dict[str, int] = field(default_factory=dict)
    provider: str = "openai"


class LLMClientError(Exception):
    pass


class LLMCircuitOpenError(LLMClientError):
    pass


async def _enforce_rate_limit() -> None:
    global _last_request_at
    async with _rate_lock:
        now = time.monotonic()
        gap = settings.llm_min_request_interval_seconds - (now - _last_request_at)
        if gap > 0:
            await asyncio.sleep(gap)
        _last_request_at = time.monotonic()


class LLMClient:
    OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        circuit_threshold: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self.timeout = timeout or float(settings.agent_timeout_seconds)
        self.max_retries = max_retries or settings.agent_max_retries
        self.circuit_breaker = CircuitBreaker(
            threshold=circuit_threshold or settings.agent_circuit_breaker_threshold
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_key_here")

    @property
    def primary_provider(self) -> str:
        if settings.llm_primary_provider == "openai" and self.is_configured:
            return "openai"
        return "none"

    async def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> LLMResponse:
        if settings.llm_primary_provider != "openai":
            raise LLMClientError(f"Unsupported LLM provider: {settings.llm_primary_provider}")
        return await self._openai_chat_completion(system_prompt, user_prompt, temperature)

    async def _openai_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> LLMResponse:
        if not self.is_configured:
            raise LLMClientError("OpenAI API key not configured")

        if not self.circuit_breaker.can_execute():
            raise LLMCircuitOpenError("LLM circuit breaker is open")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        last_error: Exception | None = None
        start = time.monotonic()
        max_attempts = self.max_retries + 2

        for attempt in range(1, max_attempts + 1):
            await _enforce_rate_limit()
            try:
                timeout = httpx.Timeout(self.timeout, connect=5.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        self.OPENAI_CHAT_URL,
                        headers=headers,
                        json=payload,
                    )
                    if response.status_code == 429:
                        wait = settings.llm_429_backoff_seconds * (2 ** (attempt - 1))
                        logger.warning(
                            "llm_rate_limited",
                            attempt=attempt,
                            wait_seconds=wait,
                        )
                        await asyncio.sleep(wait)
                        last_error = httpx.HTTPStatusError(
                            "429 Too Many Requests",
                            request=response.request,
                            response=response,
                        )
                        continue
                    response.raise_for_status()
                    data = response.json()

                content = data["choices"][0]["message"]["content"]
                latency_ms = (time.monotonic() - start) * 1000
                usage = data.get("usage", {})

                self.circuit_breaker.record_success()
                return LLMResponse(
                    content=content,
                    model=self.model,
                    latency_ms=latency_ms,
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                    },
                    provider="openai",
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code == 429:
                    continue
                self.circuit_breaker.record_failure()
                logger.warning("llm_request_failed", attempt=attempt, error=str(exc))
            except Exception as exc:
                last_error = exc
                self.circuit_breaker.record_failure()
                logger.warning("llm_request_failed", attempt=attempt, error=str(exc))

            if attempt < max_attempts:
                await asyncio.sleep(min(2**attempt, 8))

        raise LLMClientError(f"LLM request failed after retries: {last_error}")

    async def structured_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        temperature: float = 0.2,
        *,
        symbol: str | None = None,
    ) -> tuple[T, LLMResponse]:
        response = await self.chat_completion(system_prompt, user_prompt, temperature)
        try:
            from app.schemas.agent import AgentLLMOutput, CombinedAgentLLMOutput, TeamDiscussionLLMOutput
            from app.utils.agent_llm_parse import (
                parse_agent_llm_json,
                parse_combined_agent_llm_json,
                parse_team_discussion_json,
            )

            if schema is TeamDiscussionLLMOutput or schema.__name__ == "TeamDiscussionLLMOutput":
                parsed_model = parse_team_discussion_json(response.content, symbol=symbol)
                return parsed_model, response

            if schema is CombinedAgentLLMOutput or schema.__name__ == "CombinedAgentLLMOutput":
                parsed_model = parse_combined_agent_llm_json(response.content, symbol=symbol)
                return parsed_model, response

            if schema is AgentLLMOutput or schema.__name__ == "AgentLLMOutput":
                parsed_model = parse_agent_llm_json(response.content, symbol=symbol)
                return parsed_model, response

            parsed = json.loads(response.content)
            return schema.model_validate(parsed), response
        except Exception as exc:
            raise LLMClientError(f"Failed to parse LLM response: {exc}") from exc


llm_client = LLMClient()
