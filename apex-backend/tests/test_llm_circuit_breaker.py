"""Tests for Redis-backed OpenAI circuit breaker."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.utils import llm_circuit_breaker as cb

_store: dict[str, Any] = {}


@pytest.fixture(autouse=True)
def _mock_redis() -> Any:
    async def fake_get(key: str) -> Any | None:
        return _store.get(key)

    async def fake_set(key: str, value: Any, ttl: int | None = None) -> None:
        _store[key] = value

    async def fake_delete(key: str) -> None:
        _store.pop(key, None)

    _store.clear()

    with patch("app.utils.llm_circuit_breaker.cache_get", new=fake_get):
        with patch("app.utils.llm_circuit_breaker.cache_set", new=fake_set):
            with patch("app.utils.llm_circuit_breaker.cache_delete", new=fake_delete):
                yield

    _store.clear()


@pytest.mark.asyncio
async def test_open_circuit_blocks_llm() -> None:
    await cb.open_llm_circuit(reason="429")
    assert await cb.is_llm_blocked() is True
    with pytest.raises(cb.LLMCircuitOpenError):
        await cb.assert_llm_allowed()


@pytest.mark.asyncio
async def test_success_closes_circuit() -> None:
    await cb.open_llm_circuit(reason="429")
    await cb.record_llm_success()
    status = await cb.get_circuit_status()
    assert status.state == cb.LLMCircuitState.CLOSED
    await cb.assert_llm_allowed()


@pytest.mark.asyncio
async def test_half_open_allows_single_probe() -> None:
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    _store[cb._REDIS_KEY] = {"open_until": past.isoformat(), "reason": "429"}

    with patch("app.core.redis_client.get_redis", new=AsyncMock()) as mock_redis:
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(side_effect=[True, False])
        mock_redis.return_value = mock_client

        status = await cb.get_circuit_status()
        assert status.state == cb.LLMCircuitState.HALF_OPEN
        await cb.assert_llm_allowed()
        with pytest.raises(cb.LLMCircuitOpenError):
            await cb.assert_llm_allowed()


@pytest.mark.asyncio
async def test_probe_failure_reopens_for_another_hour() -> None:
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    _store[cb._REDIS_KEY] = {"open_until": past.isoformat(), "reason": "429"}
    await cb.record_llm_probe_failure()
    status = await cb.get_circuit_status()
    assert status.state == cb.LLMCircuitState.OPEN
    assert status.remaining_seconds is not None
    assert status.remaining_seconds > 3500
