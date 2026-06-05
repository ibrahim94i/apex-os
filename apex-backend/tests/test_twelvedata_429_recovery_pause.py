"""Tests for TwelveData 429 feed recovery pause."""

from unittest.mock import AsyncMock, patch

import pytest

from app.feeds.twelvedata_limiter import (
    clear_feed_recovery_pause,
    is_feed_recovery_paused,
    record_twelvedata_429,
)
from app.services.feed_health_service import recover_feed, run_recovery_cycle


@pytest.fixture(autouse=True)
def _clear_pause() -> None:
    clear_feed_recovery_pause()
    yield
    clear_feed_recovery_pause()


def test_record_twelvedata_429_pauses_recovery() -> None:
    assert is_feed_recovery_paused() is False
    record_twelvedata_429()
    assert is_feed_recovery_paused() is True


@pytest.mark.asyncio
async def test_recover_feed_skipped_during_429_pause() -> None:
    record_twelvedata_429()
    with patch("app.services.feed_health_service.feed_manager") as mock_mgr:
        mock_mgr.restart_feed = AsyncMock(return_value=True)
        ok = await recover_feed("XAUUSD", "test")
    assert ok is False
    mock_mgr.restart_feed.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_recovery_cycle_skipped_during_429_pause() -> None:
    record_twelvedata_429()
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
