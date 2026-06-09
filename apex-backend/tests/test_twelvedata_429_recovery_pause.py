"""Tests for TwelveData 429 feed recovery pause."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.feeds import twelvedata_limiter
from app.feeds.twelvedata_limiter import (
    _CreditState,
    clear_feed_recovery_pause,
    is_feed_recovery_paused,
    record_twelvedata_429,
)
from app.services.feed_health_service import recover_feed, run_recovery_cycle

_redis_store: dict[str, Any] = {}


@pytest.fixture(autouse=True)
def _mock_redis_credits() -> Any:
    async def fake_get(key: str) -> Any | None:
        return _redis_store.get(key)

    async def fake_set(key: str, value: Any, ttl: int | None = None) -> None:
        _redis_store[key] = value

    async def fake_delete(key: str) -> None:
        _redis_store.pop(key, None)

    _redis_store.clear()
    clear_feed_recovery_pause()
    twelvedata_limiter._credit_state = _CreditState()

    with patch("app.feeds.twelvedata_limiter.cache_get", new=fake_get):
        with patch("app.feeds.twelvedata_limiter.cache_set", new=fake_set):
            with patch("app.feeds.twelvedata_limiter.cache_delete", new=fake_delete):
                yield

    _redis_store.clear()
    clear_feed_recovery_pause()
    twelvedata_limiter._credit_state = _CreditState()


@pytest.mark.asyncio
async def test_record_twelvedata_429_pauses_recovery() -> None:
    assert is_feed_recovery_paused() is False
    await record_twelvedata_429()
    assert is_feed_recovery_paused() is True


@pytest.mark.asyncio
async def test_recover_feed_skipped_during_429_pause() -> None:
    await record_twelvedata_429()
    with patch("app.services.feed_health_service.feed_manager") as mock_mgr:
        mock_mgr.restart_feed = AsyncMock(return_value=True)
        ok = await recover_feed("XAUUSD", "test")
    assert ok is False
    mock_mgr.restart_feed.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_recovery_cycle_skipped_during_429_pause() -> None:
    await record_twelvedata_429()
    with patch(
        "app.services.feed_health_service.check_feed_health",
        new=AsyncMock(
            return_value=type(
                "Status",
                (),
                {
                    "feed_running": False,
                    "market_open": True,
                    "stale": True,
                    "in_cooldown": False,
                    "age_seconds": 9999,
                    "last_update": None,
                    "recovered": False,
                },
            )()
        ),
    ):
        report = await run_recovery_cycle()
    assert any("twelvedata_429_pause" in action for action in report.actions)
