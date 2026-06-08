"""Per-asset poll intervals and feed-type split."""

from app.config.assets import (
    ACTIVE_SYMBOLS,
    ASSETS,
    EURUSD_POLL_INTERVAL_SECONDS,
    POLL_INTERVAL_SECONDS,
)


def test_btcusdt_binance_rest_poll_three_minutes() -> None:
    asset = ASSETS["BTCUSDT"]
    assert asset.feed_type == "binance"
    assert asset.poll_interval == POLL_INTERVAL_SECONDS
    assert asset.market_schedule == "24_7"


def test_xauusd_twelvedata_poll_three_minutes() -> None:
    asset = ASSETS["XAUUSD"]
    assert asset.feed_type == "twelvedata"
    assert asset.twelvedata_symbol == "XAU/USD"
    assert asset.poll_interval == POLL_INTERVAL_SECONDS
    assert asset.poll_interval == 180


def test_eurusd_twelvedata_poll_five_minutes() -> None:
    asset = ASSETS["EURUSD"]
    assert asset.feed_type == "twelvedata"
    assert asset.twelvedata_symbol == "EUR/USD"
    assert asset.poll_interval == EURUSD_POLL_INTERVAL_SECONDS
    assert asset.poll_interval == 300


def test_twelvedata_daily_live_poll_budget_within_free_tier() -> None:
    """Live polls use outputsize=1 → 1 credit each (bootstrap is separate)."""
    xau_calls = 86400 // ASSETS["XAUUSD"].poll_interval
    eur_calls = 86400 // ASSETS["EURUSD"].poll_interval
    assert xau_calls == 480
    assert eur_calls == 288
    assert xau_calls + eur_calls == 768


def test_usdjpy_gbpusd_use_frankfurter() -> None:
    for symbol in ("USDJPY", "GBPUSD"):
        asset = ASSETS[symbol]
        assert asset.feed_type == "frankfurter"
        assert asset.frankfurter_from_symbol
        assert asset.frankfurter_to_symbol
        assert asset.poll_interval == POLL_INTERVAL_SECONDS
        assert asset.twelvedata_symbol is None


def test_finnhub_symbols_kept_for_news() -> None:
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].finnhub_symbol
        assert ASSETS[symbol].finnhub_symbol.startswith("OANDA:")
