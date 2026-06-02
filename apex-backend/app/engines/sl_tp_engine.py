"""Stop-loss and take-profit calculation engine."""

from dataclasses import dataclass

from app.config import settings
from app.config.assets import get_asset
from app.schemas import IndicatorSnapshotSchema, RegimeType, SignalDirection


@dataclass
class SLTPResult:
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float


class SLTPEngine:
    """ATR-based SL/TP with regime-aware multipliers."""

    DEFAULT_ATR_SL_MULTIPLIER = 1.5
    DEFAULT_ATR_TP_MULTIPLIER = 3.0

    REGIME_SL_MULTIPLIERS: dict[RegimeType, float] = {
        RegimeType.TRENDING_UP: 1.5,
        RegimeType.TRENDING_DOWN: 1.5,
        RegimeType.RANGING: 1.0,
        RegimeType.VOLATILE: 2.0,
        RegimeType.UNKNOWN: 1.5,
    }

    REGIME_TP_MULTIPLIERS: dict[RegimeType, float] = {
        RegimeType.TRENDING_UP: 3.0,
        RegimeType.TRENDING_DOWN: 3.0,
        RegimeType.RANGING: 1.5,
        RegimeType.VOLATILE: 2.0,
        RegimeType.UNKNOWN: 2.0,
    }

    def calculate(
        self,
        entry_price: float,
        direction: SignalDirection,
        indicators: IndicatorSnapshotSchema,
        regime: RegimeType,
    ) -> SLTPResult:
        atr = indicators.atr or (entry_price * 0.01)

        sl_mult = self.REGIME_SL_MULTIPLIERS.get(regime, self.DEFAULT_ATR_SL_MULTIPLIER)
        tp_mult = self.REGIME_TP_MULTIPLIERS.get(regime, self.DEFAULT_ATR_TP_MULTIPLIER)

        if direction == SignalDirection.LONG:
            stop_loss = entry_price - (atr * sl_mult)
            take_profit = entry_price + (atr * tp_mult)
        elif direction == SignalDirection.SHORT:
            stop_loss = entry_price + (atr * sl_mult)
            take_profit = entry_price - (atr * tp_mult)
        else:
            stop_loss = entry_price
            take_profit = entry_price

        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        min_rr = settings.min_risk_reward_ratio
        if risk > 0 and reward / risk < min_rr:
            min_reward = risk * min_rr
            if direction == SignalDirection.LONG:
                take_profit = entry_price + min_reward
            elif direction == SignalDirection.SHORT:
                take_profit = entry_price - min_reward
            reward = min_reward

        rr_ratio = reward / risk if risk > 0 else 0.0

        asset = get_asset(indicators.symbol)
        decimals = asset.price_decimals if asset else 2

        return SLTPResult(
            entry_price=round(entry_price, decimals),
            stop_loss=round(stop_loss, decimals),
            take_profit=round(take_profit, decimals),
            risk_reward_ratio=round(rr_ratio, 2),
        )
