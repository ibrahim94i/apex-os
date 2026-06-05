"""Per-asset TwelveData poll intervals."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS

POLL_INTERVAL_SECONDS = 480


def test_all_active_assets_poll_every_eight_minutes() -> None:
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].poll_interval == POLL_INTERVAL_SECONDS


def test_all_active_assets_have_expected_intervals() -> None:
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].poll_interval == POLL_INTERVAL_SECONDS
