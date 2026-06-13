"""Tests for MetaTrader-first analysis price resolution in get_latest_price()."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.cache import get_latest_price


@pytest.mark.asyncio
async def test_get_latest_price_prefers_fresh_metatrader() -> None:
    fresh_mt = {
        "symbol": "XAUUSD",
        "bid": 4193.8,
        "ask": 4194.01,
        "price": 4193.905,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "metatrader",
    }
    feed = {"price": 4180.0, "timestamp": "2026-06-12T00:00:00+00:00", "source": "twelvedata"}

    with patch("app.core.cache.get_metatrader_price", new=AsyncMock(return_value=fresh_mt)):
        with patch("app.core.cache.cache_get", new=AsyncMock(return_value=feed)):
            data = await get_latest_price("XAUUSD")

    assert data is not None
    assert data["source"] == "metatrader"
    assert data["price"] == pytest.approx(4193.905)
    assert data["bid"] == pytest.approx(4193.8)


@pytest.mark.asyncio
async def test_get_latest_price_falls_back_when_metatrader_stale() -> None:
    stale_mt = {
        "symbol": "XAUUSD",
        "price": 4190.0,
        "received_at": (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(),
        "source": "metatrader",
    }
    feed = {"price": 4185.5, "timestamp": "2026-06-12T00:00:00+00:00", "source": "binance"}

    with patch("app.core.cache.get_metatrader_price", new=AsyncMock(return_value=stale_mt)):
        with patch("app.core.cache.cache_get", new=AsyncMock(return_value=feed)):
            data = await get_latest_price("XAUUSD")

    assert data is not None
    assert data["source"] == "binance"
    assert data["price"] == pytest.approx(4185.5)


@pytest.mark.asyncio
async def test_get_latest_price_falls_back_when_metatrader_missing() -> None:
    feed = {"price": 4200.0, "timestamp": "2026-06-12T00:00:00+00:00", "source": "twelvedata"}

    with patch("app.core.cache.get_metatrader_price", new=AsyncMock(return_value=None)):
        with patch("app.core.cache.cache_get", new=AsyncMock(return_value=feed)):
            data = await get_latest_price("XAUUSD")

    assert data is not None
    assert data["price"] == pytest.approx(4200.0)
    assert data["source"] == "twelvedata"
