"""Tests for feed status age recomputation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.feed_status import get_all_feed_statuses


@pytest.mark.asyncio
async def test_get_all_feed_statuses_clamps_future_age_to_zero() -> None:
    future = (datetime.now(timezone.utc) + timedelta(hours=9)).isoformat()
    cached = {
        "symbol": "XAUUSD",
        "status": "connected",
        "status_ar": "متصل",
        "last_update": future,
        "age_seconds": -34000,
        "consecutive_failures": 0,
    }
    with patch("app.services.feed_status.get_feed_status", new_callable=AsyncMock, return_value=cached):
        out = await get_all_feed_statuses(["XAUUSD"])
    assert out["XAUUSD"]["age_seconds"] == 0


@pytest.mark.asyncio
async def test_get_all_feed_statuses_uses_poll_received_at() -> None:
    poll_at = datetime.now(timezone.utc).isoformat()
    bar_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    cached = {
        "symbol": "BTCUSDT",
        "status": "connected",
        "status_ar": "متصل",
        "last_update": bar_at,
        "poll_received_at": poll_at,
        "age_seconds": 9999,
        "consecutive_failures": 0,
    }
    with patch("app.services.feed_status.get_feed_status", new_callable=AsyncMock, return_value=cached):
        out = await get_all_feed_statuses(["BTCUSDT"])
    assert out["BTCUSDT"]["age_seconds"] is not None
    assert out["BTCUSDT"]["age_seconds"] < 10


@pytest.mark.asyncio
async def test_get_all_feed_statuses_recomputes_stale_age() -> None:
    past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    cached = {
        "symbol": "EURUSD",
        "status": "connected",
        "status_ar": "متصل",
        "last_update": past,
        "poll_received_at": past,
        "age_seconds": 0,
        "consecutive_failures": 0,
    }
    with patch("app.services.feed_status.get_feed_status", new_callable=AsyncMock, return_value=cached):
        out = await get_all_feed_statuses(["EURUSD"])
    assert out["EURUSD"]["age_seconds"] >= 590
