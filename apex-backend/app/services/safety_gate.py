"""Mandatory safety gate — blocks signals against dominant trend / extreme ADX."""

from __future__ import annotations

from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType, SignalDirection

ADX_EXTREME_THRESHOLD = 50.0


def check_mandatory_safety_gate(
    direction: SignalDirection,
    regime: RegimeSnapshotSchema,
    indicators: IndicatorSnapshotSchema,
    price: float,
) -> tuple[bool, str | None]:
    """
    Return (allowed, rejection_reason).
    Blocks LONG/SHORT when any mandatory condition is met.
    """
    if direction == SignalDirection.NEUTRAL:
        return False, "neutral_direction"

    adx = indicators.adx if indicators.adx is not None else regime.adx_value
    ema200 = indicators.ema_200

    if direction == SignalDirection.LONG:
        if regime.regime == RegimeType.TRENDING_DOWN:
            return False, "safety_gate_long_trending_down"
        if adx is not None and adx > ADX_EXTREME_THRESHOLD:
            return False, "safety_gate_long_adx_extreme"
        if ema200 is not None and price < ema200:
            return False, "safety_gate_long_below_ema200"

    if direction == SignalDirection.SHORT:
        if regime.regime == RegimeType.TRENDING_UP:
            return False, "safety_gate_short_trending_up"
        if adx is not None and adx > ADX_EXTREME_THRESHOLD:
            return False, "safety_gate_short_adx_extreme"
        if ema200 is not None and price > ema200:
            return False, "safety_gate_short_above_ema200"

    return True, None
