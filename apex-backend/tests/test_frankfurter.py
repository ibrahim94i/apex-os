"""Tests for Frankfurter EURUSD feed and active symbols."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS
from app.feeds.frankfurter_client import build_hourly_bar
from app.services.signal_rejection_i18n import rejection_reason_ar


def test_btcusdt_not_in_active_symbols() -> None:
    assert "BTCUSDT" not in ACTIVE_SYMBOLS
    assert ACTIVE_SYMBOLS == ["XAUUSD", "EURUSD"]
    assert "BTCUSDT" in ASSETS


def test_eurusd_uses_frankfurter_feed() -> None:
    asset = ASSETS["EURUSD"]
    assert asset.feed_type == "frankfurter"
    assert asset.frankfurter_from_symbol == "EUR"
    assert asset.frankfurter_to_symbol == "USD"


def test_build_hourly_bar() -> None:
    bar = build_hourly_bar(apex_symbol="EURUSD", price=1.085)
    assert bar["symbol"] == "EURUSD"
    assert bar["close"] == 1.085
    assert bar["source"] == "frankfurter"


def test_rejection_reason_ar() -> None:
    msg = rejection_reason_ar("safety_gate_long_trending_down")
    assert msg is not None
    assert "Safety Gate" in msg or "اتجاه هابط" in msg
