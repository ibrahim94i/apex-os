"""Unit tests for risk calculator and SL/TP engine."""

from app.engines.risk_calculator import RiskCalculator
from app.engines.sl_tp_engine import SLTPEngine
from app.schemas import IndicatorSnapshotSchema, RegimeType, SignalDirection
from datetime import datetime, timezone


def test_risk_calculator_position_size() -> None:
    calc = RiskCalculator(account_balance=10000, max_risk_pct=1.0)
    result = calc.calculate(entry_price=50000, stop_loss=49500, direction="LONG")
    assert result.risk_amount == 100.0
    assert result.units > 0
    assert result.position_size > 0


def test_sl_tp_engine_long() -> None:
    engine = SLTPEngine()
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        atr=500.0,
    )
    result = engine.calculate(50000, SignalDirection.LONG, indicators, RegimeType.TRENDING_UP)
    assert result.stop_loss < result.entry_price
    assert result.take_profit > result.entry_price
    assert result.risk_reward_ratio >= 2.0


def test_sl_tp_engine_short() -> None:
    engine = SLTPEngine()
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        atr=500.0,
    )
    result = engine.calculate(50000, SignalDirection.SHORT, indicators, RegimeType.TRENDING_DOWN)
    assert result.stop_loss > result.entry_price
    assert result.take_profit < result.entry_price
