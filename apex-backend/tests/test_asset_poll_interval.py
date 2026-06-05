"""Per-asset poll intervals and feed-type split."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS, POLL_INTERVAL_SECONDS


def test_all_active_assets_poll_every_three_minutes() -> None:
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].poll_interval == POLL_INTERVAL_SECONDS
        assert ASSETS[symbol].poll_interval == 180


def test_gold_uses_twelvedata_only() -> None:
    asset = ASSETS["XAUUSD"]
    assert asset.feed_type == "twelvedata"
    assert asset.twelvedata_symbol == "XAU/USD"


def test_fx_pairs_use_frankfurter() -> None:
    for symbol in ("EURUSD", "USDJPY", "GBPUSD"):
        asset = ASSETS[symbol]
        assert asset.feed_type == "frankfurter"
        assert asset.frankfurter_from_symbol
        assert asset.frankfurter_to_symbol
        assert asset.twelvedata_symbol is None


def test_finnhub_symbols_kept_for_news() -> None:
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].finnhub_symbol
        assert ASSETS[symbol].finnhub_symbol.startswith("OANDA:")
