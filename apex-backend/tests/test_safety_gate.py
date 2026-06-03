"""Tests for mandatory safety gate."""

from datetime import datetime, timezone

import pytest

from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.services.safety_gate import check_mandatory_safety_gate


def _indicators(**kwargs: float | None) -> IndicatorSnapshotSchema:
    base = {
        "symbol": "BTCUSDT",
        "timestamp": datetime.now(timezone.utc),
        "ema_200": 90000.0,
        "adx": 30.0,
    }
    base.update(kwargs)
    return IndicatorSnapshotSchema(**base)


def _regime(regime: RegimeType, adx: float | None = 30.0) -> RegimeSnapshotSchema:
    return RegimeSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        regime=regime,
        confidence=0.8,
        adx_value=adx,
    )


def test_long_blocked_in_trending_down() -> None:
    ok, reason = check_mandatory_safety_gate(
        SignalDirection.LONG,
        _regime(RegimeType.TRENDING_DOWN),
        _indicators(),
        price=95000.0,
    )
    assert ok is False
    assert reason == "safety_gate_long_trending_down"


def test_long_blocked_adx_above_50() -> None:
    ok, reason = check_mandatory_safety_gate(
        SignalDirection.LONG,
        _regime(RegimeType.TRENDING_UP),
        _indicators(adx=55.0),
        price=95000.0,
    )
    assert ok is False
    assert reason == "safety_gate_long_adx_extreme"


def test_long_blocked_below_ema200() -> None:
    ok, reason = check_mandatory_safety_gate(
        SignalDirection.LONG,
        _regime(RegimeType.TRENDING_UP),
        _indicators(ema_200=96000.0),
        price=95000.0,
    )
    assert ok is False
    assert reason == "safety_gate_long_below_ema200"


def test_short_blocked_in_trending_up() -> None:
    ok, reason = check_mandatory_safety_gate(
        SignalDirection.SHORT,
        _regime(RegimeType.TRENDING_UP),
        _indicators(),
        price=95000.0,
    )
    assert ok is False
    assert reason == "safety_gate_short_trending_up"


def test_short_blocked_adx_above_50() -> None:
    ok, reason = check_mandatory_safety_gate(
        SignalDirection.SHORT,
        _regime(RegimeType.TRENDING_DOWN),
        _indicators(adx=51.0),
        price=95000.0,
    )
    assert ok is False
    assert reason == "safety_gate_short_adx_extreme"


def test_short_blocked_above_ema200() -> None:
    ok, reason = check_mandatory_safety_gate(
        SignalDirection.SHORT,
        _regime(RegimeType.TRENDING_DOWN),
        _indicators(ema_200=94000.0),
        price=95000.0,
    )
    assert ok is False
    assert reason == "safety_gate_short_above_ema200"


def test_long_allowed_when_safe() -> None:
    ok, reason = check_mandatory_safety_gate(
        SignalDirection.LONG,
        _regime(RegimeType.TRENDING_UP),
        _indicators(ema_200=94000.0, adx=40.0),
        price=95000.0,
    )
    assert ok is True
    assert reason is None


def test_short_allowed_when_safe() -> None:
    ok, reason = check_mandatory_safety_gate(
        SignalDirection.SHORT,
        _regime(RegimeType.TRENDING_DOWN),
        _indicators(ema_200=96000.0, adx=35.0),
        price=95000.0,
    )
    assert ok is True
    assert reason is None
