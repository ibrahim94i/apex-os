"""Per-asset TwelveData poll intervals."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS

XAUUSD_POLL_SECONDS = 60
FX_POLL_SECONDS = 300


def test_xauusd_polls_every_minute() -> None:
    assert ASSETS["XAUUSD"].poll_interval == XAUUSD_POLL_SECONDS


def test_fx_pairs_poll_every_five_minutes() -> None:
    for symbol in ("EURUSD", "USDJPY", "GBPUSD"):
        assert ASSETS[symbol].poll_interval == FX_POLL_SECONDS


def test_all_active_assets_have_expected_intervals() -> None:
    expected = {
        "XAUUSD": XAUUSD_POLL_SECONDS,
        "EURUSD": FX_POLL_SECONDS,
        "USDJPY": FX_POLL_SECONDS,
        "GBPUSD": FX_POLL_SECONDS,
    }
    for symbol in ACTIVE_SYMBOLS:
        assert ASSETS[symbol].poll_interval == expected[symbol]
