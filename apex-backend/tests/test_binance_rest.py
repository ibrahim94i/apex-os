"""Tests for Binance REST klines client and feed."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.binance_client import fetch_binance_klines, fetch_binance_latest_bar, kline_row_to_bar
from app.feeds.binance_rest import BinanceRestFeed
from app.feeds.manager import feed_manager

KLINE_ROW = [
    1700000000000,
    "95000.00",
    "95100.00",
    "94900.00",
    "95050.00",
    "100.5",
    1700003599999,
    "9550000",
    1000,
    "50.0",
    "4750000",
    "0",
]


def test_kline_row_to_bar() -> None:
    bar = kline_row_to_bar("BTCUSDT", KLINE_ROW)
    assert bar["symbol"] == "BTCUSDT"
    assert bar["close"] == 95050.0
    assert bar["source"] == "binance"
    assert "is_closed" in bar


@pytest.mark.asyncio
async def test_fetch_binance_latest_bar() -> None:
    with patch(
        "app.feeds.binance_client.fetch_binance_klines",
        new=AsyncMock(return_value=[{"symbol": "BTCUSDT", "close": 95000.0}]),
    ):
        bar = await fetch_binance_latest_bar("BTCUSDT")
    assert bar is not None
    assert bar["close"] == 95000.0


@pytest.mark.asyncio
async def test_binance_rest_feed_poll_once() -> None:
    feed = BinanceRestFeed(symbol="BTCUSDT", poll_interval=180)
    mock_bar = {
        "symbol": "BTCUSDT",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "open": 95000.0,
        "high": 95100.0,
        "low": 94900.0,
        "close": 95050.0,
        "volume": 100.0,
        "source": "binance",
        "is_closed": False,
    }
    with patch(
        "app.feeds.binance_rest.fetch_binance_latest_bar",
        new=AsyncMock(return_value=mock_bar),
    ):
        with patch("app.feeds.binance_rest.set_latest_price", new=AsyncMock()):
            with patch("app.feeds.binance_rest.set_feed_last_update", new=AsyncMock()):
                with patch("app.feeds.binance_rest.set_feed_status", new=AsyncMock()):
                    ok = await feed._poll_once()
    assert ok is True


def test_btcusdt_uses_binance_rest_feed() -> None:
    asset = ASSETS["BTCUSDT"]
    assert asset.feed_type == "binance"
    assert asset.poll_interval == 180
    assert asset.market_schedule == "24_7"
    assert asset.twelvedata_symbol is None
    feed = feed_manager._create_feed(asset)
    assert isinstance(feed, BinanceRestFeed)
    assert feed.poll_interval == 180
