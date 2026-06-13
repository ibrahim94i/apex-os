"""Tests for market hours schedule."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.market_hours import (
    is_market_open,
    next_market_close,
    next_market_open,
    next_signal_opportunity,
    pipeline_blocked_by_market_hours,
)

BAGHDAD = ZoneInfo("Asia/Baghdad")


def _iraq(y, m, d, h, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=BAGHDAD).astimezone(timezone.utc)


def test_btc_always_open() -> None:
    assert is_market_open("BTCUSDT") is True
    assert next_market_open("BTCUSDT") is None


def test_gold_open_tuesday() -> None:
    dt = _iraq(2026, 6, 2, 10)  # Tuesday 10 AM Iraq
    assert is_market_open("XAUUSD", dt) is True


def test_gold_closed_saturday() -> None:
    dt = _iraq(2026, 6, 6, 12)  # Saturday
    assert is_market_open("XAUUSD", dt) is False


def test_gold_closed_sunday() -> None:
    dt = _iraq(2026, 6, 7, 12)  # Sunday
    assert is_market_open("XAUUSD", dt) is False


def test_gold_closed_friday_night() -> None:
    dt = _iraq(2026, 6, 5, 23, 30)  # Friday 11:30 PM
    assert is_market_open("XAUUSD", dt) is False


def test_gold_closed_monday_early() -> None:
    dt = _iraq(2026, 6, 8, 0, 30)  # Monday 12:30 AM
    assert is_market_open("XAUUSD", dt) is False


def test_gold_opens_monday_1am() -> None:
    dt = _iraq(2026, 6, 8, 1, 0)  # Monday 1:00 AM
    assert is_market_open("XAUUSD", dt) is True


def test_pipeline_blocked_respects_testing_flag() -> None:
    from app.config import settings

    sat = _iraq(2026, 6, 6, 15)
    assert is_market_open("XAUUSD", sat) is False
    original = settings.agents_run_when_market_closed
    try:
        settings.agents_run_when_market_closed = False
        assert pipeline_blocked_by_market_hours("XAUUSD", sat) is True
        settings.agents_run_when_market_closed = True
        assert pipeline_blocked_by_market_hours("XAUUSD", sat) is False
    finally:
        settings.agents_run_when_market_closed = original


def test_next_open_from_saturday() -> None:
    sat = _iraq(2026, 6, 6, 15)
    nxt = next_market_open("XAUUSD", sat)
    assert nxt is not None
    local = nxt.astimezone(BAGHDAD)
    assert local.weekday() == 0 and local.hour == 1


def test_next_close_on_tuesday_is_friday_11pm() -> None:
    dt = _iraq(2026, 6, 2, 10)
    close = next_market_close("XAUUSD", dt)
    assert close is not None
    local = close.astimezone(BAGHDAD)
    assert local.weekday() == 4
    assert local.hour == 23
    assert local.minute == 0


def test_next_close_none_when_market_closed() -> None:
    sat = _iraq(2026, 6, 6, 15)
    assert next_market_close("XAUUSD", sat) is None


def test_btc_has_no_close() -> None:
    assert next_market_close("BTCUSDT") is None


def test_next_signal_none_when_closed() -> None:
    sat = _iraq(2026, 6, 6, 15)
    assert next_signal_opportunity("XAUUSD", None, 1.0, sat) is None


def test_eurusd_open_wednesday() -> None:
    dt = _iraq(2026, 6, 3, 14)  # Wednesday 2 PM
    assert is_market_open("EURUSD", dt) is True


def test_eurusd_closed_saturday() -> None:
    dt = _iraq(2026, 6, 6, 10)
    assert is_market_open("EURUSD", dt) is False


def test_eurusd_closed_sunday() -> None:
    dt = _iraq(2026, 6, 7, 10)
    assert is_market_open("EURUSD", dt) is False


def test_eurusd_open_friday_night() -> None:
    """EURUSD 24/5 stays open Friday evening (unlike gold)."""
    dt = _iraq(2026, 6, 5, 22, 0)
    assert is_market_open("EURUSD", dt) is True


def test_eurusd_next_open_from_saturday() -> None:
    sat = _iraq(2026, 6, 6, 15)
    nxt = next_market_open("EURUSD", sat)
    assert nxt is not None
    local = nxt.astimezone(BAGHDAD)
    assert local.weekday() == 0 and local.hour == 0
