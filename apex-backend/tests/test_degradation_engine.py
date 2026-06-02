"""Unit tests for degradation engine."""

from datetime import datetime, timezone

from app.engines.degradation_engine import DegradationEngine
from app.schemas import (
    IndicatorSnapshotSchema,
    KillSwitchStatus,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
    RegimeType,
    SignalDirection,
)


def test_degradation_kill_switch_zeroes_confidence() -> None:
    engine = DegradationEngine()
    regime = RegimeSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        regime=RegimeType.TRENDING_UP,
        confidence=0.8,
    )
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
    )
    ks = KillSwitchStatusSchema(status=KillSwitchStatus.ACTIVE, reason="Test")
    result = engine.degrade(0.8, SignalDirection.LONG, regime, indicators, ks)
    assert result.confidence == 0.0
    assert result.degraded is True


def test_degradation_volatile_regime() -> None:
    engine = DegradationEngine()
    regime = RegimeSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        regime=RegimeType.VOLATILE,
        confidence=0.7,
    )
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
    )
    ks = KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE)
    result = engine.degrade(0.8, SignalDirection.LONG, regime, indicators, ks)
    assert result.confidence == round(0.8 * 0.7, 4)
    assert result.degraded is True
