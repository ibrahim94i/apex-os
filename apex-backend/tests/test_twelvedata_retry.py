"""TwelveData feed uses resilient live bar resolver."""

from unittest.mock import AsyncMock, patch

import pytest

from app.feeds.twelvedata import TwelveDataFeed


@pytest.mark.asyncio
async def test_poll_once_uses_resolver() -> None:
    feed = TwelveDataFeed(api_key="test-key", symbol="EUR/USD", apex_symbol="EURUSD", interval="1h")
    bar = {
        "symbol": "EURUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 1.08,
        "high": 1.09,
        "low": 1.07,
        "close": 1.085,
        "volume": 0.0,
        "source": "finnhub",
        "is_closed": True,
    }
    with patch(
        "app.feeds.twelvedata.fetch_live_bar_with_fallback",
        new=AsyncMock(return_value=(bar, "finnhub")),
    ):
        with patch.object(feed, "_publish_bar", new=AsyncMock()) as mock_publish:
            ok = await feed._poll_once()
    assert ok is True
    mock_publish.assert_awaited_once_with(bar, "finnhub")
