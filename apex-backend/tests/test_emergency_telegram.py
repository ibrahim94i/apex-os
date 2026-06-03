"""Tests for emergency position conflict detection."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.position_service import detect_position_signal_conflict


def _pos(direction: str) -> SimpleNamespace:
    return SimpleNamespace(direction=direction, outcome=None)


def test_no_conflict_below_threshold() -> None:
    alert, kind = detect_position_signal_conflict([_pos("SHORT")], "LONG", 0.70)
    assert alert is False
    assert kind is None


def test_bullish_conflict_open_short_strong_long() -> None:
    alert, kind = detect_position_signal_conflict([_pos("SHORT")], "LONG", 0.80)
    assert alert is True
    assert kind == "market_turned_bullish"


def test_bearish_conflict_open_long_strong_short() -> None:
    alert, kind = detect_position_signal_conflict([_pos("LONG")], "SHORT", 0.85)
    assert alert is True
    assert kind == "market_turned_bearish"


def test_no_conflict_same_direction() -> None:
    alert, kind = detect_position_signal_conflict([_pos("LONG")], "LONG", 0.90)
    assert alert is False
