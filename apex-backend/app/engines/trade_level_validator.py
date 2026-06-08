"""Trade Level Validator — SL/TP placement and distance checks after zone-based levels."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.enums import SignalDirection

_EPS = 1e-9


@dataclass(frozen=True)
class TradeLevelValidationResult:
    valid: bool
    reason: str | None = None
    detail: str | None = None


def validate_trade_levels(
    *,
    direction: SignalDirection,
    entry_price: float,
    entry_zone_low: float,
    entry_zone_high: float,
    stop_loss: float,
    take_profit: float,
    atr: float,
    min_rr: float = 2.0,
) -> TradeLevelValidationResult:
    """
    Validate SL/TP after zone-based calculation.

    BUY: SL below zone low, TP above zone high.
    SELL: SL above zone high, TP below zone low.
    All directions: min distances from entry_price and R:R >= min_rr.
    """
    if atr <= 0:
        return TradeLevelValidationResult(
            valid=False,
            reason="invalid_trade_levels",
            detail="atr_non_positive",
        )

    if direction == SignalDirection.LONG:
        if not (stop_loss < entry_zone_low - _EPS):
            return TradeLevelValidationResult(
                valid=False,
                reason="invalid_trade_levels",
                detail="buy_sl_not_below_zone_low",
            )
        if not (take_profit > entry_zone_high + _EPS):
            return TradeLevelValidationResult(
                valid=False,
                reason="invalid_trade_levels",
                detail="buy_tp_not_above_zone_high",
            )
        risk = abs(entry_zone_low - stop_loss)
        reward = abs(take_profit - entry_zone_high)
    elif direction == SignalDirection.SHORT:
        if not (stop_loss > entry_zone_high + _EPS):
            return TradeLevelValidationResult(
                valid=False,
                reason="invalid_trade_levels",
                detail="sell_sl_not_above_zone_high",
            )
        if not (take_profit < entry_zone_low - _EPS):
            return TradeLevelValidationResult(
                valid=False,
                reason="invalid_trade_levels",
                detail="sell_tp_not_below_zone_low",
            )
        risk = abs(stop_loss - entry_zone_high)
        reward = abs(entry_zone_low - take_profit)
    else:
        return TradeLevelValidationResult(
            valid=False,
            reason="invalid_trade_levels",
            detail="neutral_direction",
        )

    sl_distance = abs(entry_price - stop_loss)
    tp_distance = abs(take_profit - entry_price)

    if sl_distance + _EPS < atr:
        return TradeLevelValidationResult(
            valid=False,
            reason="invalid_trade_levels",
            detail="sl_distance_below_atr",
        )

    if tp_distance + _EPS < atr * 2:
        return TradeLevelValidationResult(
            valid=False,
            reason="invalid_trade_levels",
            detail="tp_distance_below_2atr",
        )

    if risk <= _EPS:
        return TradeLevelValidationResult(
            valid=False,
            reason="invalid_trade_levels",
            detail="zero_risk",
        )

    rr = reward / risk
    if rr + _EPS < min_rr:
        return TradeLevelValidationResult(
            valid=False,
            reason="invalid_trade_levels",
            detail=f"risk_reward_below_{min_rr}",
        )

    return TradeLevelValidationResult(valid=True)
