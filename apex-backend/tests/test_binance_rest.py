"""Tests for Binance REST klines client and feed."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.binance_client import (
    BINANCE_KLINES_URLS,
    fetch_binance_klines,
    fetch_binance_latest_bar,
    fetch_binance_ticker_price,
    kline_row_to_bar,
)
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


def test_binance_uses_vision_mirror_first() -> None:
    assert "data-api.binance.vision" in BINANCE_KLINES_URLS[0]


@pytest.mark.asyncio
async def test_fetch_binance_klines_tries_next_endpoint_on_451() -> None:
    ok_response = MagicMock()
    ok_response.raise_for_status = MagicMock()
    ok_response.json.return_value = [KLINE_ROW]

    fail_response = MagicMock()
    fail_response.raise_for_status.side_effect = Exception("451")

    async def fake_get(url, params=None):
        if "data-api.binance.vision" in url:
            raise Exception("451")
        return ok_response

    with patch("app.feeds.binance_client.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=fake_get)
        bars = await fetch_binance_klines("BTCUSDT", limit=1)
    assert len(bars) == 1
    assert bars[0]["close"] == 95050.0


@pytest.mark.asyncio
async def test_fetch_binance_latest_bar_falls_back_to_ticker() -> None:
    with patch(
        "app.feeds.binance_client.fetch_binance_klines",
        new=AsyncMock(side_effect=RuntimeError("all klines failed")),
    ):
        with patch(
            "app.feeds.binance_client.fetch_binance_ticker_price",
            new=AsyncMock(return_value=61800.0),
        ):
            bar = await fetch_binance_latest_bar("BTCUSDT")
    assert bar is not None
    assert bar["close"] == 61800.0


@pytest.mark.asyncio
async def test_binance_rest_feed_poll_once_uses_poll_time_for_price() -> None:
    feed = BinanceRestFeed(symbol="BTCUSDT", poll_interval=180)
    mock_bar = {
        "symbol": "BTCUSDT",
        "timestamp": "2026-06-05T21:00:00+00:00",
        "open": 95000.0,
        "high": 95100.0,
        "low": 94900.0,
        "close": 95050.0,
        "volume": 100.0,
        "source": "binance",
        "is_closed": False,
    }
    mock_set_price = AsyncMock()
    mock_set_update = AsyncMock()
    with patch(
        "app.feeds.binance_rest.fetch_binance_latest_bar",
        new=AsyncMock(return_value=mock_bar),
    ):
        with patch("app.feeds.binance_rest.set_latest_price", mock_set_price):
            with patch("app.feeds.binance_rest.set_feed_last_update", mock_set_update):
                with patch("app.feeds.binance_rest.set_feed_status", new=AsyncMock()):
                    ok = await feed._poll_once()
    assert ok is True
    price_ts = mock_set_price.await_args.args[2]
    update_kwargs = mock_set_update.await_args.kwargs
    assert price_ts != mock_bar["timestamp"]
    assert update_kwargs["received_at"] == price_ts


def test_btcusdt_uses_binance_rest_feed() -> None:
    asset = ASSETS["BTCUSDT"]
    assert asset.feed_type == "binance"
    assert asset.poll_interval == 180
    feed = feed_manager._create_feed(asset)
    assert isinstance(feed, BinanceRestFeed)
    assert feed.poll_interval == 180
