"""Mandatory safety gate — blocks signals against dominant trend / EMA200."""

from __future__ import annotations

from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType, SignalDirection


def check_mandatory_safety_gate(
    direction: SignalDirection,
    regime: RegimeSnapshotSchema,
    indicators: IndicatorSnapshotSchema,
    price: float,
) -> tuple[bool, str | None]:
    """
    Return (allowed, rejection_reason).
    Strong ADX (trend) aligns with signal when regime matches direction — never block on ADX alone.
    """
    if direction == SignalDirection.NEUTRAL:
        return False, "neutral_direction"

    ema200 = indicators.ema_200

    if direction == SignalDirection.LONG:
        if regime.regime == RegimeType.TRENDING_DOWN:
            return False, "safety_gate_long_trending_down"
        if ema200 is not None and price < ema200:
            return False, "safety_gate_long_below_ema200"

    if direction == SignalDirection.SHORT:
        if regime.regime == RegimeType.TRENDING_UP:
            return False, "safety_gate_short_trending_up"
        if ema200 is not None and price > ema200:
            return False, "safety_gate_short_above_ema200"

    return True, None
