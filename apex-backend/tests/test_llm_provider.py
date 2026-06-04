"""Tests for Groq-only LLM client."""

from unittest.mock import AsyncMock, patch

import pytest

from app.utils.llm_client import LLMClient, LLMResponse


@pytest.mark.asyncio
async def test_primary_provider_is_groq_when_configured() -> None:
    client = LLMClient(api_key="test-groq-key")
    assert client.primary_provider == "groq"
    assert client.is_configured is True


@pytest.mark.asyncio
async def test_primary_provider_none_without_key() -> None:
    client = LLMClient(api_key="your_key_here")
    assert client.primary_provider == "none"
    assert client.is_configured is False


@pytest.mark.asyncio
async def test_chat_completion_uses_groq() -> None:
    client = LLMClient(api_key="test-key")
    groq_response = LLMResponse(content="{}", model="llama", latency_ms=50, provider="groq")

    with patch.object(client, "_groq_chat_completion", new_callable=AsyncMock, return_value=groq_response):
        response = await client.chat_completion("sys", "user")

    assert response.provider == "groq"
