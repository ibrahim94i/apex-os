"""Tests for Binance futures H1 kline WebSocket feed."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.binance_futures_kline_ws import (
    BinanceFuturesKlineWsFeed,
    parse_futures_kline_message,
)
from app.feeds.manager import feed_manager


def test_parse_futures_kline_message() -> None:
    payload = {
        "e": "kline",
        "E": 1718112000123,
        "s": "XAUUSDT",
        "k": {
            "t": 1718112000000,
            "T": 1718115599999,
            "s": "XAUUSDT",
            "i": "1h",
            "o": "4070.0",
            "h": "4075.0",
            "l": "4068.0",
            "c": "4072.5",
            "v": "123.4",
            "x": True,
        },
    }
    bar = parse_futures_kline_message(
        json.dumps(payload),
        binance_symbol="XAUUSDT",
        apex_symbol="XAUUSD",
    )
    assert bar is not None
    assert bar["symbol"] == "XAUUSD"
    assert bar["close"] == 4072.5
    assert bar["source"] == "binance"
    assert bar["is_closed"] is True


def test_xauusd_uses_futures_kline_ws_feed() -> None:
    asset = ASSETS["XAUUSD"]
    feed = feed_manager._create_feed(asset)
    assert isinstance(feed, BinanceFuturesKlineWsFeed)
    assert feed.binance_symbol == "XAUUSDT"
    assert "xauusdt@kline_1h" in feed.ws_url


@pytest.mark.asyncio
async def test_handle_message_publishes_bar() -> None:
    feed = BinanceFuturesKlineWsFeed(
        ws_url="wss://fstream.binance.com/ws/xauusdt@kline_1h",
        binance_symbol="XAUUSDT",
        apex_symbol="XAUUSD",
    )
    payload = {
        "e": "kline",
        "k": {
            "t": 1718112000000,
            "s": "XAUUSDT",
            "o": "4070.0",
            "h": "4075.0",
            "l": "4068.0",
            "c": "4072.5",
            "v": "1.0",
            "x": False,
        },
    }
    with patch.object(feed, "_publish_bar", new=AsyncMock()) as mock_publish:
        await feed._handle_message(json.dumps(payload))
    mock_publish.assert_awaited_once()
