"""OpenAI LLM client with global serialization, Redis circuit breaker, and 429 handling."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.config import settings
from app.logging_config import logger
from app.utils.llm_circuit_breaker import (
    LLMCircuitOpenError,
    assert_llm_allowed,
    get_circuit_status,
    is_llm_blocked,
    record_llm_429,
    record_llm_probe_failure,
    record_llm_success,
)

T = TypeVar("T", bound=BaseModel)

_llm_global_lock = asyncio.Lock()
_rate_lock = asyncio.Lock()
_last_request_at: float = 0.0


@dataclass
class LLMResponse:
    content: str
    model: str
    latency_ms: float
    usage: dict[str, int] = field(default_factory=dict)
    provider: str = "openai"


class LLMClientError(Exception):
    pass


# Re-export for callers that import from llm_client.


async def _enforce_rate_limit() -> None:
    global _last_request_at
    async with _rate_lock:
        now = time.monotonic()
        gap = settings.llm_min_request_interval_seconds - (now - _last_request_at)
        if gap > 0:
            await asyncio.sleep(gap)
        _last_request_at = time.monotonic()


async def _handle_http_429() -> None:
    status = await get_circuit_status()
    if status.state.value == "half_open":
        await record_llm_probe_failure()
    else:
        await record_llm_429()
    raise LLMClientError("LLM request failed: 429 Too Many Requests")


class LLMClient:
    OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
    OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

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
        _ = circuit_threshold  # legacy param — Redis circuit breaker replaces in-memory threshold

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

        async with _llm_global_lock:
            await assert_llm_allowed()

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
            max_attempts = self.max_retries + 1

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
                            logger.warning("llm_rate_limited", attempt=attempt, action="circuit_open")
                            await _handle_http_429()
                        response.raise_for_status()
                        data = response.json()

                    content = data["choices"][0]["message"]["content"]
                    latency_ms = (time.monotonic() - start) * 1000
                    usage = data.get("usage", {})

                    await record_llm_success()
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
                except LLMClientError:
                    raise
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code == 429:
                        await _handle_http_429()
                    logger.warning("llm_request_failed", attempt=attempt, error=str(exc))
                except Exception as exc:
                    last_error = exc
                    logger.warning("llm_request_failed", attempt=attempt, error=str(exc))

                if attempt < max_attempts:
                    await asyncio.sleep(min(2**attempt, 8))

            status = await get_circuit_status()
            if status.state.value == "half_open":
                await record_llm_probe_failure()
            raise LLMClientError(f"LLM request failed after retries: {last_error}")

    @staticmethod
    def _extract_responses_text(data: dict) -> str:
        parts: list[str] = []
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for block in item.get("content", []):
                if block.get("type") == "output_text" and block.get("text"):
                    parts.append(block["text"])
        if parts:
            return "\n".join(parts).strip()
        if data.get("output_text"):
            return str(data["output_text"]).strip()
        raise LLMClientError("Empty response from OpenAI Responses API")

    async def advisor_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float = 0.3,
    ) -> LLMResponse:
        if not self.is_configured:
            raise LLMClientError("OpenAI API key not configured")

        async with _llm_global_lock:
            await assert_llm_allowed()

            messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                for item in conversation_history:
                    if item.get("role") in ("user", "assistant") and item.get("content"):
                        messages.append({"role": item["role"], "content": item["content"]})
            messages.append({"role": "user", "content": user_prompt})

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "temperature": temperature,
                "messages": messages,
            }

            advisor_timeout = float(getattr(settings, "advisor_timeout_seconds", 90))
            last_error: Exception | None = None
            start = time.monotonic()
            max_attempts = self.max_retries + 1

            for attempt in range(1, max_attempts + 1):
                await _enforce_rate_limit()
                try:
                    timeout = httpx.Timeout(advisor_timeout, connect=10.0)
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(
                            self.OPENAI_CHAT_URL,
                            headers=headers,
                            json=payload,
                        )
                        if response.status_code == 429:
                            logger.warning("advisor_rate_limited", attempt=attempt, action="circuit_open")
                            await _handle_http_429()
                        response.raise_for_status()
                        data = response.json()

                    content = data["choices"][0]["message"]["content"]
                    latency_ms = (time.monotonic() - start) * 1000
                    usage = data.get("usage", {})
                    await record_llm_success()
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
                except LLMClientError:
                    raise
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code == 429:
                        await _handle_http_429()
                    logger.warning("advisor_chat_failed", attempt=attempt, error=str(exc))
                except Exception as exc:
                    last_error = exc
                    logger.warning("advisor_chat_failed", attempt=attempt, error=str(exc))

                if attempt < max_attempts:
                    await asyncio.sleep(min(2**attempt, 8))

            status = await get_circuit_status()
            if status.state.value == "half_open":
                await record_llm_probe_failure()
            raise LLMClientError(f"Advisor chat failed after retries: {last_error}")

    async def advisor_chat_with_web_search(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float = 0.3,
    ) -> LLMResponse:
        if not self.is_configured:
            raise LLMClientError("OpenAI API key not configured")

        async with _llm_global_lock:
            await assert_llm_allowed()

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            input_payload: list[dict[str, str]] | str
            if conversation_history:
                input_payload = [
                    {"role": m["role"], "content": m["content"]}
                    for m in conversation_history
                    if m.get("role") in ("user", "assistant") and m.get("content")
                ]
                input_payload.append({"role": "user", "content": user_prompt})
            else:
                input_payload = user_prompt

            payload = {
                "model": self.model,
                "instructions": system_prompt,
                "tools": [{"type": "web_search_preview"}],
                "input": input_payload,
                "temperature": temperature,
            }

            advisor_timeout = float(getattr(settings, "advisor_timeout_seconds", 90))
            last_error: Exception | None = None
            start = time.monotonic()
            max_attempts = self.max_retries + 1

            for attempt in range(1, max_attempts + 1):
                await _enforce_rate_limit()
                try:
                    timeout = httpx.Timeout(advisor_timeout, connect=10.0)
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(
                            self.OPENAI_RESPONSES_URL,
                            headers=headers,
                            json=payload,
                        )
                        if response.status_code == 429:
                            logger.warning(
                                "advisor_rate_limited",
                                attempt=attempt,
                                action="circuit_open",
                            )
                            await _handle_http_429()
                        response.raise_for_status()
                        data = response.json()

                    content = self._extract_responses_text(data)
                    latency_ms = (time.monotonic() - start) * 1000
                    usage = data.get("usage", {})
                    await record_llm_success()
                    return LLMResponse(
                        content=content,
                        model=self.model,
                        latency_ms=latency_ms,
                        usage={
                            "prompt_tokens": usage.get("input_tokens", 0),
                            "completion_tokens": usage.get("output_tokens", 0),
                        },
                        provider="openai_web",
                    )
                except LLMClientError:
                    raise
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    body = exc.response.text[:300] if exc.response else ""
                    logger.warning(
                        "advisor_web_search_failed",
                        attempt=attempt,
                        status=exc.response.status_code if exc.response else None,
                        body=body,
                    )
                    if exc.response.status_code == 429:
                        await _handle_http_429()
                except Exception as exc:
                    last_error = exc
                    logger.warning("advisor_web_search_failed", attempt=attempt, error=str(exc))

                if attempt < max_attempts:
                    await asyncio.sleep(min(2**attempt, 8))

            status = await get_circuit_status()
            if status.state.value == "half_open":
                await record_llm_probe_failure()
            logger.warning("advisor_falling_back_to_chat_without_web_search")
            fallback = await self._openai_chat_completion_plain(system_prompt, user_prompt, temperature)
            fallback.provider = "openai"
            return fallback

    async def _openai_chat_completion_plain(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> LLMResponse:
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
        }
        advisor_timeout = float(getattr(settings, "advisor_timeout_seconds", 90))
        start = time.monotonic()
        timeout = httpx.Timeout(advisor_timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self.OPENAI_CHAT_URL, headers=headers, json=payload)
            if response.status_code == 429:
                await _handle_http_429()
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        await record_llm_success()
        return LLMResponse(
            content=content,
            model=self.model,
            latency_ms=(time.monotonic() - start) * 1000,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            provider="openai",
        )

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
