"""Final Decision Gate — SNR veto first, then agent consensus on breakout."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.engines.indicator_engine import OHLCVBar
from app.engines.snr_engine import SNREngine
from app.schemas.agent import AgentConsensus
from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRSnapshotSchema
from app.utils.price_zones import level_zone_bounds

SNRState = Literal["WAIT", "BREAKOUT_CONFIRMED", "NORMAL"]
FinalAction = Literal["NO_TRADE", "BUY", "SELL"]


@dataclass(frozen=True)
class FinalDecisionResult:
    action: FinalAction
    snr_state: SNRState
    reason: str | None = None
    direction: SignalDirection | None = None
    confidence: float | None = None


def classify_snr_state(
    bars: list[OHLCVBar],
    snr: SNRSnapshotSchema | None,
) -> SNRState:
    """SNR decides first: in zone = WAIT, confirmed breakout = BREAKOUT, else NORMAL."""
    if not bars or snr is None:
        return "NORMAL"

    price = bars[-1].close
    in_zone, _, _ = SNREngine._price_in_level_zone(price, snr)
    if in_zone:
        return "WAIT"

    if snr.resistance_1 is not None:
        _, r1_high = level_zone_bounds(snr.resistance_1)
        if SNREngine._confirmed_bullish_breakout(bars, r1_high):
            return "BREAKOUT_CONFIRMED"

    if snr.support_1 is not None:
        s1_low, _ = level_zone_bounds(snr.support_1)
        if SNREngine._confirmed_bearish_breakout(bars, s1_low):
            return "BREAKOUT_CONFIRMED"

    return "NORMAL"


def finalize_decision(
    snr_state: SNRState,
    agent_consensus: AgentConsensus | None,
) -> FinalDecisionResult:
    """
    Merge SNR state with agent consensus.

    SNR WAIT is an absolute veto — no trade even at 100% agent confidence.
    On BREAKOUT_CONFIRMED, agent consensus determines BUY/SELL.
    NORMAL yields NO_TRADE until a confirmed breakout occurs.
    """
    if snr_state == "WAIT":
        return FinalDecisionResult(
            action="NO_TRADE",
            snr_state=snr_state,
            reason="SNR Zone Block",
        )

    if snr_state == "BREAKOUT_CONFIRMED":
        if agent_consensus is None:
            return FinalDecisionResult(
                action="NO_TRADE",
                snr_state=snr_state,
                reason="no_agent_consensus",
            )
        if agent_consensus.final_direction == SignalDirection.LONG:
            return FinalDecisionResult(
                action="BUY",
                snr_state=snr_state,
                direction=SignalDirection.LONG,
                confidence=agent_consensus.final_confidence,
            )
        if agent_consensus.final_direction == SignalDirection.SHORT:
            return FinalDecisionResult(
                action="SELL",
                snr_state=snr_state,
                direction=SignalDirection.SHORT,
                confidence=agent_consensus.final_confidence,
            )
        return FinalDecisionResult(
            action="NO_TRADE",
            snr_state=snr_state,
            reason="neutral_direction",
        )

    return FinalDecisionResult(
        action="NO_TRADE",
        snr_state=snr_state,
        reason="snr_awaiting_breakout",
    )


def final_decision_label_ar(action: FinalAction) -> str:
    return {
        "NO_TRADE": "لا تداول",
        "BUY": "شراء",
        "SELL": "بيع",
    }[action]


def snr_state_label_ar(state: SNRState) -> str:
    return {
        "WAIT": "انتظار",
        "BREAKOUT_CONFIRMED": "كسر مؤكد",
        "NORMAL": "عادي",
    }[state]


def apply_final_decision_to_consensus(
    consensus: AgentConsensus,
    *,
    bars: list[OHLCVBar],
    snr: SNRSnapshotSchema | None,
) -> AgentConsensus:
    """Attach SNR state + final decision to consensus for dashboard/API."""
    snr_state = classify_snr_state(bars, snr)
    final = finalize_decision(snr_state, consensus)

    updates: dict[str, Any] = {
        "snr_state": snr_state,
        "final_decision": final.action,
        "final_decision_ar": final_decision_label_ar(final.action),
        "snr_state_ar": snr_state_label_ar(snr_state),
    }

    if final.action == "NO_TRADE":
        updates["signal_decision"] = "wait"
        updates["rejection_reason"] = final.reason
        from app.services.signal_rejection_i18n import rejection_reason_ar

        updates["rejection_reason_ar"] = rejection_reason_ar(final.reason)
        updates["proposed_direction"] = consensus.final_direction
        updates["proposed_confidence"] = consensus.final_confidence
    else:
        updates["proposed_direction"] = final.direction
        updates["proposed_confidence"] = final.confidence

    return consensus.model_copy(update=updates)
