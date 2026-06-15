"""Final Decision Gate — SNR soft filter, then agent consensus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.engines.indicator_engine import OHLCVBar
from app.engines.snr_engine import SNREngine
from app.schemas.agent import AgentConsensus
from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRSnapshotSchema
from app.utils.price_zones import level_zone_bounds, price_in_level_zone

SNRState = Literal["INSIDE_ZONE", "ZONE_EDGE", "BREAKOUT_CONFIRMED", "NORMAL"]
FinalAction = Literal["NO_TRADE", "BUY", "SELL"]

ZONE_EDGE_THRESHOLD_PCT = 0.1
INSIDE_ZONE_PENALTY = 0.20
ZONE_EDGE_PENALTY = 0.10

SNR_WARNINGS_AR: dict[SNRState, str | None] = {
    "INSIDE_ZONE": "تحذير — السعر داخل منطقة SNR",
    "ZONE_EDGE": "السعر قريب من كسر المنطقة",
    "BREAKOUT_CONFIRMED": None,
    "NORMAL": None,
}


@dataclass(frozen=True)
class FinalDecisionResult:
    action: FinalAction
    snr_state: SNRState
    reason: str | None = None
    direction: SignalDirection | None = None
    confidence: float | None = None
    raw_confidence: float | None = None
    confidence_penalty: float = 0.0
    snr_warning_ar: str | None = None


def resolve_snr_evaluation_price(
    bars: list[OHLCVBar],
    snr: SNRSnapshotSchema | None,
    *,
    current_price: float | None = None,
) -> float | None:
    """Single source of truth for SNR state — prefer live/bar price over snapshot price."""
    if current_price is not None and current_price > 0:
        return current_price
    if bars:
        close = bars[-1].close
        if close > 0:
            return close
    if snr is not None and snr.price is not None and snr.price > 0:
        return snr.price
    return None


def _snr_levels(snr: SNRSnapshotSchema) -> list[float]:
    return [
        level
        for level in (
            snr.support_1,
            snr.support_2,
            snr.support_3,
            snr.resistance_1,
            snr.resistance_2,
            snr.resistance_3,
        )
        if level is not None and level > 0
    ]


def _price_inside_any_zone(price: float, snr: SNRSnapshotSchema) -> bool:
    return any(price_in_level_zone(price, level) for level in _snr_levels(snr))


def _distance_pct(price: float, boundary: float) -> float:
    if boundary <= 0:
        return float("inf")
    return abs(price - boundary) / boundary * 100.0


def _is_zone_edge(price: float, snr: SNRSnapshotSchema) -> bool:
    """Outside all zones but within 0.1% of any zone boundary."""
    if _price_inside_any_zone(price, snr):
        return False

    min_dist: float | None = None
    for level in _snr_levels(snr):
        low, high = level_zone_bounds(level)
        for boundary in (low, high):
            dist = _distance_pct(price, boundary)
            if min_dist is None or dist < min_dist:
                min_dist = dist

    return min_dist is not None and min_dist < ZONE_EDGE_THRESHOLD_PCT


def classify_snr_state(
    bars: list[OHLCVBar],
    snr: SNRSnapshotSchema | None,
    *,
    current_price: float | None = None,
) -> SNRState:
    """SNR soft filter: breakout > inside zone > near edge > normal."""
    if not bars or snr is None:
        return "NORMAL"

    if snr.resistance_1 is not None:
        _, r1_high = level_zone_bounds(snr.resistance_1)
        if SNREngine._confirmed_bullish_breakout(bars, r1_high):
            return "BREAKOUT_CONFIRMED"

    if snr.support_1 is not None:
        s1_low, _ = level_zone_bounds(snr.support_1)
        if SNREngine._confirmed_bearish_breakout(bars, s1_low):
            return "BREAKOUT_CONFIRMED"

    price = resolve_snr_evaluation_price(bars, snr, current_price=current_price)
    if price is None:
        return "NORMAL"

    if _price_inside_any_zone(price, snr):
        return "INSIDE_ZONE"

    if _is_zone_edge(price, snr):
        return "ZONE_EDGE"

    return "NORMAL"


def snr_confidence_penalty(snr_state: SNRState) -> float:
    if snr_state == "INSIDE_ZONE":
        return INSIDE_ZONE_PENALTY
    if snr_state == "ZONE_EDGE":
        return ZONE_EDGE_PENALTY
    return 0.0


def snr_penalty_points(snr_state: SNRState | str) -> int:
    """Stored on each signal: -20, -10, or 0."""
    state = snr_state.upper() if isinstance(snr_state, str) else snr_state
    return int(-snr_confidence_penalty(state) * 100)  # type: ignore[arg-type]


def snr_state_record_value(snr_state: SNRState | str) -> str:
    """Stored on each signal: inside_zone / zone_edge / breakout_confirmed / normal."""
    return snr_state.lower() if isinstance(snr_state, str) else snr_state.lower()


def apply_snr_confidence_penalty(confidence: float, snr_state: SNRState) -> float:
    penalty = snr_confidence_penalty(snr_state)
    adjusted = confidence * (1.0 - penalty)
    return round(max(0.0, min(1.0, adjusted)), 4)


def finalize_decision(
    snr_state: SNRState,
    agent_consensus: AgentConsensus | None,
) -> FinalDecisionResult:
    """Merge SNR soft filter with agent consensus — SNR adjusts confidence only."""
    warning = SNR_WARNINGS_AR.get(snr_state)

    if agent_consensus is None:
        return FinalDecisionResult(
            action="NO_TRADE",
            snr_state=snr_state,
            reason="no_agent_consensus",
            snr_warning_ar=warning,
        )

    if agent_consensus.final_direction == SignalDirection.NEUTRAL:
        return FinalDecisionResult(
            action="NO_TRADE",
            snr_state=snr_state,
            reason="neutral_direction",
            snr_warning_ar=warning,
        )

    penalty = snr_confidence_penalty(snr_state)
    adjusted = apply_snr_confidence_penalty(
        agent_consensus.final_confidence,
        snr_state,
    )

    if agent_consensus.final_direction == SignalDirection.LONG:
        return FinalDecisionResult(
            action="BUY",
            snr_state=snr_state,
            direction=SignalDirection.LONG,
            confidence=adjusted,
            raw_confidence=agent_consensus.final_confidence,
            confidence_penalty=penalty,
            snr_warning_ar=warning,
        )

    return FinalDecisionResult(
        action="SELL",
        snr_state=snr_state,
        direction=SignalDirection.SHORT,
        confidence=adjusted,
        raw_confidence=agent_consensus.final_confidence,
        confidence_penalty=penalty,
        snr_warning_ar=warning,
    )


def final_decision_label_ar(action: FinalAction) -> str:
    return {
        "NO_TRADE": "لا تداول",
        "BUY": "شراء",
        "SELL": "بيع",
    }[action]


def snr_state_label_ar(state: SNRState) -> str:
    return {
        "INSIDE_ZONE": "داخل المنطقة",
        "ZONE_EDGE": "قرب الكسر",
        "BREAKOUT_CONFIRMED": "كسر مؤكد",
        "NORMAL": "عادي",
    }[state]


def apply_final_decision_to_consensus(
    consensus: AgentConsensus,
    *,
    bars: list[OHLCVBar],
    snr: SNRSnapshotSchema | None,
    current_price: float | None = None,
) -> AgentConsensus:
    """Attach SNR state, soft-filter warning, and final decision to consensus."""
    snr_state = classify_snr_state(bars, snr, current_price=current_price)
    final = finalize_decision(snr_state, consensus)

    updates: dict[str, Any] = {
        "snr_state": snr_state,
        "snr_state_ar": snr_state_label_ar(snr_state),
        "final_decision": final.action,
        "final_decision_ar": final_decision_label_ar(final.action),
        "snr_warning_ar": final.snr_warning_ar,
    }

    if final.action == "NO_TRADE":
        updates["proposed_direction"] = consensus.final_direction
        updates["proposed_confidence"] = consensus.final_confidence
        if final.reason and final.reason not in (
            "neutral_direction",
            "no_agent_consensus",
        ):
            from app.services.signal_rejection_i18n import rejection_reason_ar

            updates["rejection_reason"] = final.reason
            updates["rejection_reason_ar"] = rejection_reason_ar(final.reason)
    else:
        updates["proposed_direction"] = final.direction
        updates["proposed_confidence"] = final.confidence
        updates["rejection_reason"] = None
        updates["rejection_reason_ar"] = None

    from app.services.signal_rejection_i18n import normalize_snr_consensus_fields

    rr, rr_ar, warning = normalize_snr_consensus_fields(
        rejection_reason=updates.get("rejection_reason"),
        rejection_reason_ar=updates.get("rejection_reason_ar"),
        snr_warning_ar=updates.get("snr_warning_ar"),
        final_decision=updates.get("final_decision"),
    )
    updates["rejection_reason"] = rr
    updates["rejection_reason_ar"] = rr_ar
    updates["snr_warning_ar"] = warning

    return consensus.model_copy(update=updates)
