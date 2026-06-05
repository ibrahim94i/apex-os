"""Tests for active symbols and feed config."""

from app.config.assets import (
    ACTIVE_SYMBOLS,
    ASSETS,
    EURUSD_POLL_INTERVAL_SECONDS,
    POLL_INTERVAL_SECONDS,
)
from app.services.signal_rejection_i18n import rejection_reason_ar


def test_btcusdt_not_in_active_symbols() -> None:
    assert "BTCUSDT" not in ACTIVE_SYMBOLS
    assert ACTIVE_SYMBOLS == ["XAUUSD", "EURUSD", "USDJPY", "GBPUSD"]
    assert "BTCUSDT" in ASSETS


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
