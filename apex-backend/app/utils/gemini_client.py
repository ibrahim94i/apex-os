"""Google Gemini client via google-generativeai SDK."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from app.config import settings
from app.logging_config import logger
from app.utils.llm_client import LLMClientError, LLMResponse


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.timeout = timeout or float(settings.agent_timeout_seconds)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key not in ("", "your_key_here"))

    def _generate_sync(self, system_prompt: str, user_prompt: str, temperature: float) -> dict[str, Any]:
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_prompt,
        )
        response = model.generate_content(
            user_prompt,
            generation_config={
                "temperature": temperature,
                "response_mime_type": "application/json",
            },
            request_options={"timeout": self.timeout},
        )
        text = response.text or ""
        if not text.strip():
            raise LLMClientError("Gemini returned empty response")
        return {"content": text, "model": self.model}

    async def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> LLMResponse:
        if not self.is_configured:
            raise LLMClientError("Gemini API key not configured")

        start = time.monotonic()
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(self._generate_sync, system_prompt, user_prompt, temperature),
                timeout=self.timeout + 5,
            )
        except asyncio.TimeoutError as exc:
            raise LLMClientError("Gemini request timed out") from exc
        except Exception as exc:
            logger.warning("gemini_request_failed", error=str(exc))
            raise LLMClientError(f"Gemini request failed: {exc}") from exc

        latency_ms = (time.monotonic() - start) * 1000
        return LLMResponse(
            content=data["content"],
            model=data["model"],
            latency_ms=latency_ms,
            usage={},
            provider="gemini",
        )


gemini_client = GeminiClient()
