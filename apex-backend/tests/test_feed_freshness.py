"""Tests for feed poll freshness (received_at vs candle timestamp)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.feed_freshness import (
    feed_poll_age_seconds,
    feed_staleness_limit_seconds,
    is_feed_poll_stale,
)


def test_feed_poll_age_uses_received_at_not_bar_time() -> None:
    bar_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    received = datetime.now(timezone.utc).isoformat()
    age = feed_poll_age_seconds({"timestamp": bar_ts, "received_at": received})
    assert age is not None
    assert age < 5


def test_feed_poll_age_falls_back_to_timestamp() -> None:
    recent = datetime.now(timezone.utc).isoformat()
    age = feed_poll_age_seconds({"timestamp": recent})
    assert age is not None
    assert age < 5


def test_xauusd_staleness_limit_at_least_poll_interval() -> None:
    assert feed_staleness_limit_seconds("XAUUSD") >= 180 * 3


@pytest.mark.asyncio
async def test_hourly_bar_not_stale_when_poll_recent() -> None:
    bar_ts = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    received = datetime.now(timezone.utc).isoformat()
    with patch(
        "app.services.feed_freshness.get_feed_last_update",
        new=AsyncMock(return_value={"timestamp": bar_ts, "received_at": received}),
    ), patch("app.services.feed_freshness.is_market_open", return_value=True):
        assert await is_feed_poll_stale("XAUUSD") is False


@pytest.mark.asyncio
async def test_feed_not_stale_when_market_closed() -> None:
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    with patch(
        "app.services.feed_freshness.get_feed_last_update",
        new=AsyncMock(return_value={"timestamp": old, "received_at": old}),
    ), patch("app.services.feed_freshness.is_market_open", return_value=False):
        assert await is_feed_poll_stale("XAUUSD") is False


@pytest.mark.asyncio
async def test_feed_stale_when_no_recent_poll() -> None:
    old_received = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    with patch(
        "app.services.feed_freshness.get_feed_last_update",
        new=AsyncMock(
            return_value={"timestamp": old_received, "received_at": old_received}
        ),
    ), patch("app.services.feed_freshness.is_market_open", return_value=True):
        assert await is_feed_poll_stale("XAUUSD") is True
