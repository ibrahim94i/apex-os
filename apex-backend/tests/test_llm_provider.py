"""Tests for LLM provider selection (Gemini primary, Groq fallback)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.utils.llm_client import LLMClient, LLMClientError, LLMResponse


@pytest.mark.asyncio
async def test_uses_gemini_when_configured() -> None:
    gemini = MagicMock()
    gemini.is_configured = True
    gemini.chat_completion = AsyncMock(
        return_value=LLMResponse(content="{}", model="gemini-1.5-flash", latency_ms=100, provider="gemini")
    )
    client = LLMClient(api_key="", gemini_client=gemini)

    with patch("app.utils.llm_client.settings") as mock_settings:
        mock_settings.llm_primary_provider = "gemini"
        response = await client.chat_completion("sys", "user")

    assert response.provider == "gemini"
    gemini.chat_completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_falls_back_to_groq_when_gemini_fails() -> None:
    gemini = MagicMock()
    gemini.is_configured = True
    gemini.chat_completion = AsyncMock(side_effect=LLMClientError("gemini down"))

    client = LLMClient(api_key="test-key", gemini_client=gemini)
    client.circuit_breaker.can_execute = lambda: True  # type: ignore[method-assign]

    groq_response = LLMResponse(content="{}", model="llama", latency_ms=50, provider="groq")

    with patch("app.utils.llm_client.settings") as mock_settings:
        mock_settings.llm_primary_provider = "gemini"
        mock_settings.groq_min_request_interval_seconds = 0
        mock_settings.groq_429_backoff_seconds = 1
        mock_settings.agent_max_retries = 0
        with patch.object(client, "_groq_chat_completion", new_callable=AsyncMock, return_value=groq_response):
            response = await client.chat_completion("sys", "user")

    assert response.provider == "groq"
