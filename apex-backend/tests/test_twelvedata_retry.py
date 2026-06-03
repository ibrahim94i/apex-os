"""Tests for TwelveData stale-data retry logic."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_fetch_retries_when_bar_stale_then_fresh() -> None:
    feed = TwelveDataFeed(api_key="test-key", symbol="BTC/USD", apex_symbol="BTCUSDT")
    stale = _bar(400)
    fresh = _bar(30)

    mock_fetch = AsyncMock(side_effect=[stale, fresh])
    with patch.object(feed, "_fetch_latest_bar", mock_fetch):
        with patch("app.feeds.twelvedata.settings") as mock_settings:
            mock_settings.feed_staleness_limit_seconds = 300
            mock_settings.twelvedata_stale_retry_count = 2
            mock_settings.twelvedata_stale_retry_delay_seconds = 0
            bar = await feed._fetch_latest_bar_with_retry()

    assert bar is fresh
    assert mock_fetch.await_count == 2


@pytest.mark.asyncio
async def test_fetch_returns_last_bar_after_retries_exhausted() -> None:
    feed = TwelveDataFeed(api_key="test-key", symbol="BTC/USD", apex_symbol="BTCUSDT")
    stale = _bar(400)

    mock_fetch = AsyncMock(return_value=stale)
    with patch.object(feed, "_fetch_latest_bar", mock_fetch):
        with patch("app.feeds.twelvedata.settings") as mock_settings:
            mock_settings.feed_staleness_limit_seconds = 300
            mock_settings.twelvedata_stale_retry_count = 1
            mock_settings.twelvedata_stale_retry_delay_seconds = 0
            bar = await feed._fetch_latest_bar_with_retry()

    assert bar is stale
    assert mock_fetch.await_count == 2
