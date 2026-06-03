"""Tests for TwelveData stale-data retry logic."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.feeds.twelvedata import TwelveDataFeed


def _bar(age_seconds: float) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {
        "symbol": "BTCUSDT",
        "timestamp": ts.isoformat(),
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }


def test_hourly_bar_not_stale_at_20_minutes() -> None:
    feed = TwelveDataFeed(api_key="test-key", symbol="BTC/USD", apex_symbol="BTCUSDT", interval="1h")
    bar = _bar(1200)
    assert feed._is_bar_stale(bar) is False


def test_hourly_bar_stale_after_90_minutes() -> None:
    feed = TwelveDataFeed(api_key="test-key", symbol="BTC/USD", apex_symbol="BTCUSDT", interval="1h")
    bar = _bar(4000)
    assert feed._is_bar_stale(bar) is True


@pytest.mark.asyncio
async def test_fetch_retries_when_bar_stale_then_fresh() -> None:
    feed = TwelveDataFeed(api_key="test-key", symbol="BTC/USD", apex_symbol="BTCUSDT", interval="1h")
    stale = _bar(4000)
    fresh = _bar(1200)

    mock_fetch = AsyncMock(side_effect=[stale, fresh])
    with patch.object(feed, "_fetch_latest_bar", mock_fetch):
        with patch("app.feeds.twelvedata.settings") as mock_settings:
            mock_settings.twelvedata_stale_retry_count = 2
            mock_settings.twelvedata_stale_retry_delay_seconds = 0
            bar = await feed._fetch_latest_bar_with_retry()

    assert bar is fresh
    assert mock_fetch.await_count == 2


@pytest.mark.asyncio
async def test_fetch_skips_retry_on_429() -> None:
    feed = TwelveDataFeed(api_key="test-key", symbol="BTC/USD", apex_symbol="BTCUSDT", interval="1h")
    request = httpx.Request("GET", "https://api.twelvedata.com/time_series")
    response = httpx.Response(429, request=request)
    err = httpx.HTTPStatusError("429", request=request, response=response)

    mock_fetch = AsyncMock(side_effect=err)
    with patch.object(feed, "_fetch_latest_bar", mock_fetch):
        with patch("app.feeds.twelvedata.settings") as mock_settings:
            mock_settings.twelvedata_stale_retry_count = 2
            mock_settings.twelvedata_stale_retry_delay_seconds = 0
            bar = await feed._fetch_latest_bar_with_retry()

    assert bar is None
    assert mock_fetch.await_count == 1
