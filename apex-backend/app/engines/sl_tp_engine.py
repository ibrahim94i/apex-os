"""Stop-loss and take-profit calculation engine."""

from dataclasses import dataclass

from app.config.assets import get_asset
from app.schemas import IndicatorSnapshotSchema, RegimeType, SignalDirection
from app.utils.price_zones import entry_zone_from_price


@dataclass
class SLTPResult:
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float


class SLTPEngine:
    """Zone-based SL/TP using entry zone bounds ± ATR."""

    def calculate(
        self,
        entry_zone_low: float,
        entry_zone_high: float,
        direction: SignalDirection,
        indicators: IndicatorSnapshotSchema,
        regime: RegimeType | None = None,
    ) -> SLTPResult:
        del regime  # zone formulas are regime-agnostic
        entry_center = (entry_zone_low + entry_zone_high) / 2.0
        atr = indicators.atr or (entry_center * 0.01)

        if direction == SignalDirection.LONG:
            stop_loss = entry_zone_low - atr
            take_profit = entry_zone_high + (atr * 2.0)
        elif direction == SignalDirection.SHORT:
            stop_loss = entry_zone_high + atr
            take_profit = entry_zone_low - (atr * 2.0)
        else:
            stop_loss = entry_center
            take_profit = entry_center

        risk = abs(entry_zone_low - stop_loss) if direction == SignalDirection.LONG else abs(
            stop_loss - entry_zone_high
        )
        reward = abs(take_profit - entry_zone_high) if direction == SignalDirection.LONG else abs(
            entry_zone_low - take_profit
        )
        rr_ratio = reward / risk if risk > 0 else 0.0

        asset = get_asset(indicators.symbol)
        decimals = asset.price_decimals if asset else 2

        return SLTPResult(
            entry_price=round(entry_center, decimals),
            stop_loss=round(stop_loss, decimals),
            take_profit=round(take_profit, decimals),
            risk_reward_ratio=round(rr_ratio, 2),
        )

    def calculate_from_entry(
        self,
        entry_price: float,
        direction: SignalDirection,
        indicators: IndicatorSnapshotSchema,
        regime: RegimeType | None = None,
    ) -> SLTPResult:
        """Backward-compatible helper when only a single entry price is available."""
        asset = get_asset(indicators.symbol)
        decimals = asset.price_decimals if asset else 2
        zone_low, zone_high, _ = entry_zone_from_price(entry_price, decimals=decimals)
        return self.calculate(zone_low, zone_high, direction, indicators, regime)
