"""Tests for active symbols and feed config."""

from app.config.assets import (
    ACTIVE_SYMBOLS,
    ASSETS,
    EURUSD_POLL_INTERVAL_SECONDS,
    POLL_INTERVAL_SECONDS,
)
from app.services.signal_rejection_i18n import rejection_reason_ar


def test_active_symbols_xauusd_only() -> None:
    assert ACTIVE_SYMBOLS == ["XAUUSD"]
    assert "BTCUSDT" not in ACTIVE_SYMBOLS
    assert "EURUSD" not in ACTIVE_SYMBOLS
    assert "GBPUSD" not in ACTIVE_SYMBOLS
    assert "USDJPY" not in ACTIVE_SYMBOLS


def test_btcusdt_uses_binance_feed() -> None:
    asset = ASSETS["BTCUSDT"]
    assert asset.feed_type == "binance"
    assert asset.poll_interval == POLL_INTERVAL_SECONDS


def test_eurusd_uses_twelvedata_feed() -> None:
    asset = ASSETS["EURUSD"]
    assert asset.feed_type == "twelvedata"
    assert asset.twelvedata_symbol == "EUR/USD"
    assert asset.poll_interval == EURUSD_POLL_INTERVAL_SECONDS
    assert asset.poll_interval == 300


def test_xauusd_uses_twelvedata_feed() -> None:
    asset = ASSETS["XAUUSD"]
    assert asset.feed_type == "twelvedata"
    assert asset.twelvedata_symbol == "XAU/USD"
    assert asset.finnhub_symbol == "OANDA:XAU_USD"
    assert asset.poll_interval == POLL_INTERVAL_SECONDS
    assert asset.poll_interval == 180


def test_rejection_reason_ar() -> None:
    msg = rejection_reason_ar("safety_gate_long_trending_down")
    assert msg is not None
    assert "Safety Gate" in msg or "اتجاه هابط" in msg
