"""Tests for Groq/OpenAI LLM client routing."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.utils.llm_client import LLMClient, LLMClientError, LLMResponse


@pytest.mark.asyncio
async def test_primary_provider_is_openai_when_configured() -> None:
    client = LLMClient(api_key="test-openai-key")
    with patch.object(settings, "llm_primary_provider", "openai"):
        assert client.primary_provider == "openai"
    assert client.is_openai_configured is True


@pytest.mark.asyncio
async def test_primary_provider_is_groq_when_configured() -> None:
    client = LLMClient(groq_api_key="test-groq-key")
    with patch.object(settings, "llm_primary_provider", "groq"):
        assert client.primary_provider == "groq"
    assert client.is_groq_configured is True


@pytest.mark.asyncio
async def test_primary_provider_none_without_key() -> None:
    client = LLMClient(api_key="your_key_here", groq_api_key="your_key_here")
    with patch.object(settings, "llm_primary_provider", "openai"):
        assert client.primary_provider == "none"
    assert client.is_configured is False


@pytest.mark.asyncio
async def test_chat_completion_uses_openai_when_primary_openai() -> None:
    client = LLMClient(api_key="test-key")
    openai_response = LLMResponse(
        content="{}", model="gpt-4o-mini", latency_ms=50, provider="openai"
    )

    with patch.object(settings, "llm_primary_provider", "openai"):
        with patch.object(
            client, "_openai_chat_completion", new_callable=AsyncMock, return_value=openai_response
        ):
            response = await client.chat_completion("sys", "user")

    assert response.provider == "openai"


@pytest.mark.asyncio
async def test_chat_completion_uses_groq_when_primary_groq() -> None:
    client = LLMClient(groq_api_key="test-groq-key")
    groq_response = LLMResponse(
        content="{}", model="llama-3.3-70b-versatile", latency_ms=40, provider="groq"
    )

    with patch.object(settings, "llm_primary_provider", "groq"):
        with patch.object(
            client, "_groq_chat_completion", new_callable=AsyncMock, return_value=groq_response
        ):
            response = await client.chat_completion("sys", "user")

    assert response.provider == "groq"


@pytest.mark.asyncio
async def test_chat_completion_falls_back_to_openai_when_groq_fails() -> None:
    client = LLMClient(api_key="test-openai-key", groq_api_key="test-groq-key")
    openai_response = LLMResponse(
        content="{}", model="gpt-4o-mini", latency_ms=50, provider="openai"
    )

    with patch.object(settings, "llm_primary_provider", "groq"):
        with patch.object(
            client,
            "_groq_chat_completion",
            new_callable=AsyncMock,
            side_effect=LLMClientError("Groq request failed: 429"),
        ):
            with patch.object(
                client,
                "_openai_chat_completion",
                new_callable=AsyncMock,
                return_value=openai_response,
            ) as openai_mock:
                response = await client.chat_completion("sys", "user")

    openai_mock.assert_awaited_once()
    assert response.provider == "openai"
