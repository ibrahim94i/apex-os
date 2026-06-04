"""Tests for OpenAI LLM client."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.utils.llm_client import LLMClient, LLMResponse


@pytest.mark.asyncio
async def test_primary_provider_is_openai_when_configured() -> None:
    client = LLMClient(api_key="test-openai-key")
    with patch.object(settings, "llm_primary_provider", "openai"):
        assert client.primary_provider == "openai"
    assert client.is_configured is True


@pytest.mark.asyncio
async def test_primary_provider_none_without_key() -> None:
    client = LLMClient(api_key="your_key_here")
    with patch.object(settings, "llm_primary_provider", "openai"):
        assert client.primary_provider == "none"
    assert client.is_configured is False


@pytest.mark.asyncio
async def test_chat_completion_uses_openai() -> None:
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
