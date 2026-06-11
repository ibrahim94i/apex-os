"""Tests for Binance dashboard display ticker (isolated from analysis pipeline)."""

from unittest.mock import ANY, AsyncMock, patch

import pytest

from app.feeds.binance_display_ticker import (
    BinanceDisplayTickerFeed,
    parse_mini_ticker_message,
)

@pytest.fixture(autouse=True)
def _mock_broadcast():
    with patch(
        "app.feeds.binance_display_ticker.broadcaster.broadcast_display_price",
        new=AsyncMock(),
    ) as mock_broadcast:
        yield mock_broadcast


def test_parse_mini_ticker_message() -> None:
    message = (
        '{"e":"24hrMiniTicker","E":1718112000123,"s":"XAUUSDT","c":"2650.12","o":"2640.00"}'
    )
    parsed = parse_mini_ticker_message(message)
    assert parsed is not None
    assert parsed["price"] == 2650.12
    assert parsed["timestamp"].endswith("+00:00")


def test_parse_mark_price_message() -> None:
    message = (
        '{"e":"markPriceUpdate","E":1718112000123,"s":"XAUUSDT","p":"2650.12","i":"XAUUSDT"}'
    )
    parsed = parse_mini_ticker_message(message)
    assert parsed is not None
    assert parsed["price"] == 2650.12


def test_parse_rest_ticker_payload() -> None:
    from app.feeds.binance_display_ticker import parse_rest_ticker_payload

    parsed = parse_rest_ticker_payload({"symbol": "XAUUSDT", "price": "4074.41", "time": 1718112000123})
    assert parsed is not None
    assert parsed["price"] == 4074.41


def test_parse_mini_ticker_rejects_other_symbol() -> None:
    message = '{"e":"24hrMiniTicker","E":1718112000123,"s":"BTCUSDT","c":"65000.0"}'
    assert parse_mini_ticker_message(message) is None


@pytest.mark.asyncio
async def test_handle_message_writes_display_price_only() -> None:
    feed = BinanceDisplayTickerFeed()
    message = (
        '{"e":"24hrMiniTicker","E":1718112000123,"s":"XAUUSDT","c":"2651.55","o":"2640.00"}'
    )

    with patch("app.feeds.binance_display_ticker.set_display_price", new=AsyncMock()) as mock_set:
        await feed._handle_message(message)

    mock_set.assert_awaited_once_with(
        "XAUUSD",
        2651.55,
        ANY,
        source="binance_xauusdt_ws",
    )


@pytest.mark.asyncio
async def test_handle_message_does_not_touch_latest_price() -> None:
    feed = BinanceDisplayTickerFeed()
    message = (
        '{"e":"24hrMiniTicker","E":1718112000123,"s":"XAUUSDT","c":"2651.55","o":"2640.00"}'
    )

    with patch("app.core.cache.set_latest_price", new=AsyncMock()) as mock_latest:
        await feed._handle_message(message)

    mock_latest.assert_not_called()
