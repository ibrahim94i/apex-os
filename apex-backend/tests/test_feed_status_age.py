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
async def test_get_all_feed_statuses_recomputes_stale_age() -> None:
    past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    cached = {
        "symbol": "EURUSD",
        "status": "connected",
        "status_ar": "متصل",
        "last_update": past,
        "age_seconds": 0,
        "consecutive_failures": 0,
    }
    with patch("app.services.feed_status.get_feed_status", new_callable=AsyncMock, return_value=cached):
        out = await get_all_feed_statuses(["EURUSD"])
    assert out["EURUSD"]["age_seconds"] >= 590
