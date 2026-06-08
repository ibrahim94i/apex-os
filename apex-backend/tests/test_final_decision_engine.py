"""Tests for Final Decision Gate — SNR veto + agent consensus on breakout."""

from datetime import datetime, timezone

from app.engines.final_decision_engine import (
    apply_final_decision_to_consensus,
    classify_snr_state,
    finalize_decision,
)
from app.engines.indicator_engine import OHLCVBar
from app.schemas.agent import AgentConsensus
from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRLevelZone, SNRSnapshotSchema
from app.utils.price_zones import level_zone_bounds


def _bar(close: float, ts: datetime | None = None) -> OHLCVBar:
    t = ts or datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
    return OHLCVBar(timestamp=t, open=close, high=close + 1, low=close - 1, close=close, volume=1.0)


def _consensus(direction: SignalDirection, confidence: float = 0.85) -> AgentConsensus:
    return AgentConsensus(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        final_direction=direction,
        final_confidence=confidence,
        verdicts=[],
        vote_scores={},
    )


def _zone(level: float) -> SNRLevelZone:
    low, high = level_zone_bounds(level)
    return SNRLevelZone(level=level, low=low, high=high)


def _snr(*, price: float, s1: float = 90.0, r1: float = 110.0) -> SNRSnapshotSchema:
    return SNRSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        price=price,
        support_1=s1,
        support_1_zone=_zone(s1),
        resistance_1=r1,
        resistance_1_zone=_zone(r1),
    )


def test_finalize_wait_is_absolute_veto() -> None:
    consensus = _consensus(SignalDirection.LONG, 1.0)
    result = finalize_decision("WAIT", consensus)
    assert result.action == "NO_TRADE"
    assert result.reason == "SNR Zone Block"


def test_finalize_breakout_returns_buy_sell_from_agents() -> None:
    buy = finalize_decision("BREAKOUT_CONFIRMED", _consensus(SignalDirection.LONG))
    sell = finalize_decision("BREAKOUT_CONFIRMED", _consensus(SignalDirection.SHORT))
    assert buy.action == "BUY"
    assert sell.action == "SELL"


def test_finalize_normal_is_no_trade() -> None:
    result = finalize_decision("NORMAL", _consensus(SignalDirection.LONG))
    assert result.action == "NO_TRADE"
    assert result.reason == "snr_awaiting_breakout"


def test_classify_wait_when_price_in_zone() -> None:
    snr = _snr(price=100.0, r1=100.0)
    bars = [_bar(100.0)]
    assert classify_snr_state(bars, snr) == "WAIT"


def test_apply_final_decision_enriches_consensus() -> None:
    snr = _snr(price=100.0, r1=100.0)
    consensus = apply_final_decision_to_consensus(
        _consensus(SignalDirection.LONG),
        bars=[_bar(100.0)],
        snr=snr,
    )
    assert consensus.snr_state == "WAIT"
    assert consensus.final_decision == "NO_TRADE"
    assert consensus.final_decision_ar == "لا تداول"
    assert consensus.signal_decision == "wait"
