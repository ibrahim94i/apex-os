"""Tests for agent data freshness and dynamic weights."""

from datetime import datetime, timezone, timedelta

import pytest

from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.snapshots import KillSwitchStatusSchema
from app.schemas.agent import AgentRole, AgentVerdict, MarketSnapshot
from app.services.agent_freshness import (
    apply_dynamic_weight_adjustments,
    is_verdict_indicator_inconsistent,
    validate_agent_data_freshness,
)


def _snapshot(**kwargs) -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    defaults = {
        "symbol": "BTCUSDT",
        "timestamp": now,
        "price": 95000.0,
        "indicators": IndicatorSnapshotSchema(symbol="BTCUSDT", timestamp=now, rsi=50.0),
        "regime": RegimeSnapshotSchema(
            symbol="BTCUSDT",
            timestamp=now,
            regime=RegimeType.TRENDING_UP,
            confidence=0.7,
        ),
        "kill_switch": KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE),
        "account_balance": 10000.0,
        "max_risk_pct": 1.0,
        "max_drawdown_pct": 5.0,
        "feed_stale": False,
    }
    defaults.update(kwargs)
    return MarketSnapshot(**defaults)


def _verdict(direction: SignalDirection = SignalDirection.LONG, **kwargs) -> AgentVerdict:
    base = {
        "agent_id": AgentRole.MARKET_ANALYST,
        "agent_name_ar": "محلل السوق",
        "direction": direction,
        "confidence": 0.8,
        "reasoning": ["اختبار"],
        "weight": 0.35,
    }
    base.update(kwargs)
    return AgentVerdict(**base)


def test_reject_when_feed_stale() -> None:
    snap = _snapshot(feed_stale=True)
    ok, reason = validate_agent_data_freshness(snap, [_verdict()])
    assert ok is False
    assert reason == "feed_stale"


def test_reject_when_snapshot_too_old() -> None:
    old_ts = datetime.now(timezone.utc) - timedelta(seconds=350)
    snap = _snapshot(timestamp=old_ts)
    ok, reason = validate_agent_data_freshness(snap, [_verdict()])
    assert ok is False
    assert reason == "snapshot_data_too_old"


def test_reject_when_verdict_marked_stale() -> None:
    snap = _snapshot()
    ok, reason = validate_agent_data_freshness(snap, [_verdict(is_stale=True)])
    assert ok is False
    assert reason == "agent_stale:market_analyst"


def test_stale_verdict_gets_reduced_weight() -> None:
    snap = _snapshot()
    verdicts = [_verdict(is_stale=True, weight=0.40)]
    adjusted, reasons = apply_dynamic_weight_adjustments(verdicts, snap.indicators, snap)
    assert adjusted[0].weight == pytest.approx(0.10, rel=0.01)
    assert any("قديمة" in r for r in reasons)


def test_inconsistent_long_detected() -> None:
    now = datetime.now(timezone.utc)
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=now,
        rsi=75.0,
        macd=-1.0,
        macd_signal=0.5,
        ema_50=94000.0,
        ema_200=96000.0,
    )
    assert is_verdict_indicator_inconsistent(_verdict(SignalDirection.LONG), indicators) is True


def test_fresh_data_passes() -> None:
    snap = _snapshot()
    ok, reason = validate_agent_data_freshness(snap, [_verdict()])
    assert ok is True
    assert reason is None
