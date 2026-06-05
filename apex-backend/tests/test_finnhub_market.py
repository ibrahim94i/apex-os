"""Tests for Finnhub market data client."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.feeds.finnhub_market import (
    _parse_candle_payload,
    fetch_finnhub_history,
    fetch_finnhub_latest_bar,
)


def test_parse_candle_payload_ok() -> None:
    ts = int(datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc).timestamp())
    bars = _parse_candle_payload(
        "EURUSD",
        {
            "s": "ok",
            "t": [ts],
            "o": [1.08],
            "h": [1.09],
            "l": [1.07],
            "c": [1.085],
            "v": [1000],
        },
    )
    assert len(bars) == 1
    assert bars[0]["symbol"] == "EURUSD"
    assert bars[0]["source"] == "finnhub"
    assert bars[0]["close"] == 1.085


@pytest.mark.asyncio
async def test_fetch_finnhub_history_returns_bars() -> None:
    ts = int(datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc).timestamp())
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "s": "ok",
        "t": [ts],
        "o": [1.08],
        "h": [1.09],
        "l": [1.07],
        "c": [1.085],
        "v": [1000],
    }

    with patch("app.feeds.finnhub_market._is_configured", return_value=True):
        with patch("app.feeds.finnhub_market._throttled_get", new=AsyncMock(return_value=mock_response)):
            bars = await fetch_finnhub_history("EURUSD", "OANDA:EUR_USD", limit=1)
    assert len(bars) == 1


@pytest.mark.asyncio
async def test_fetch_finnhub_latest_bar_uses_candles() -> None:
    ts = int(datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc).timestamp())
    bar = {
        "symbol": "XAUUSD",
        "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "open": 3300.0,
        "high": 3310.0,
        "low": 3295.0,
        "close": 3305.0,
        "volume": 0.0,
        "source": "finnhub",
        "is_closed": True,
    }
    with patch(
        "app.feeds.finnhub_market.fetch_finnhub_history",
        new=AsyncMock(return_value=[bar]),
    ):
        result = await fetch_finnhub_latest_bar("XAUUSD", "OANDA:XAU_USD")
    assert result == bar
