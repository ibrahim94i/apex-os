"""TwelveData poll interval — 4 minutes per active asset."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS

POLL_INTERVAL_SECONDS = 240


def test_active_assets_poll_four_minutes() -> None:
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].poll_interval == POLL_INTERVAL_SECONDS
