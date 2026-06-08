"""Tests for SNR soft filter and Final Decision Gate."""

from datetime import datetime, timezone

from app.engines.final_decision_engine import (
    apply_final_decision_to_consensus,
    apply_snr_confidence_penalty,
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


def test_inside_zone_reduces_confidence_not_blocks() -> None:
    consensus = _consensus(SignalDirection.LONG, 0.80)
    result = finalize_decision("INSIDE_ZONE", consensus)
    assert result.action == "BUY"
    assert result.confidence == 0.64
    assert result.snr_warning_ar == "تحذير — السعر داخل منطقة SNR"


def test_zone_edge_reduces_confidence_by_10_percent() -> None:
    consensus = _consensus(SignalDirection.SHORT, 0.90)
    result = finalize_decision("ZONE_EDGE", consensus)
    assert result.action == "SELL"
    assert result.confidence == 0.81
    assert result.snr_warning_ar == "السعر قريب من كسر المنطقة"


def test_breakout_no_penalty() -> None:
    buy = finalize_decision("BREAKOUT_CONFIRMED", _consensus(SignalDirection.LONG, 0.88))
    assert buy.action == "BUY"
    assert buy.confidence == 0.88
    assert buy.snr_warning_ar is None


def test_normal_allows_agents_without_penalty() -> None:
    result = finalize_decision("NORMAL", _consensus(SignalDirection.LONG, 0.75))
    assert result.action == "BUY"
    assert result.confidence == 0.75


def test_classify_inside_zone() -> None:
    snr = _snr(price=100.0, r1=100.0)
    assert classify_snr_state([_bar(100.0)], snr) == "INSIDE_ZONE"


def test_classify_zone_edge_outside_but_near_boundary() -> None:
    zone = _zone(100.0)
    price = zone.high * 1.0005
    snr = SNRSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        price=price,
        resistance_1=100.0,
        resistance_1_zone=zone,
    )
    assert classify_snr_state([_bar(price)], snr) == "ZONE_EDGE"


def test_apply_penalty_helper() -> None:
    assert apply_snr_confidence_penalty(1.0, "INSIDE_ZONE") == 0.8
    assert apply_snr_confidence_penalty(1.0, "ZONE_EDGE") == 0.9
    assert apply_snr_confidence_penalty(0.75, "NORMAL") == 0.75


def test_apply_final_decision_enriches_consensus_with_warning() -> None:
    snr = _snr(price=100.0, r1=100.0)
    consensus = apply_final_decision_to_consensus(
        _consensus(SignalDirection.LONG, 0.80),
        bars=[_bar(100.0)],
        snr=snr,
    )
    assert consensus.snr_state == "INSIDE_ZONE"
    assert consensus.final_decision == "BUY"
    assert consensus.proposed_confidence == 0.64
    assert consensus.snr_warning_ar == "تحذير — السعر داخل منطقة SNR"
