"""Per-asset TwelveData poll intervals."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS

POLL_INTERVAL_SECONDS = 300


def test_all_active_assets_poll_every_five_minutes() -> None:
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].poll_interval == POLL_INTERVAL_SECONDS


def test_all_active_assets_have_finnhub_symbol() -> None:
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].finnhub_symbol
        assert ASSETS[symbol].finnhub_symbol.startswith("OANDA:")
