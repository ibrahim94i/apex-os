"""Market regime classification engine."""

from dataclasses import dataclass

from app.engines.indicator_engine import OHLCVBar
from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType


@dataclass
class RegimeConfig:
    adx_trend_threshold: float = 25.0
    adx_range_threshold: float = 20.0
    volatility_high_pct: float = 2.0
    volatility_low_pct: float = 0.5


class RegimeEngine:
    """Classifies market into TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE, UNKNOWN."""

    def __init__(self, config: RegimeConfig | None = None) -> None:
        self.config = config or RegimeConfig()

    def _calc_volatility_pct(self, bars: list[OHLCVBar], lookback: int = 20) -> float:
        if len(bars) < lookback:
            return 0.0
        recent = bars[-lookback:]
        closes = [b.close for b in recent]
        mean = sum(closes) / len(closes)
        if mean == 0:
            return 0.0
        variance = sum((c - mean) ** 2 for c in closes) / len(closes)
        std = variance**0.5
        return (std / mean) * 100

    def _calc_trend_strength(self, indicators: IndicatorSnapshotSchema) -> float:
        if indicators.ema_9 is None or indicators.ema_21 is None or indicators.ema_50 is None:
            return 0.0
        alignment = 0.0
        if indicators.ema_9 > indicators.ema_21 > indicators.ema_50:
            alignment = 1.0
        elif indicators.ema_9 < indicators.ema_21 < indicators.ema_50:
            alignment = -1.0
        adx_factor = (indicators.adx or 0) / 100.0
        return alignment * adx_factor

    def classify(
        self,
        bars: list[OHLCVBar],
        indicators: IndicatorSnapshotSchema,
        symbol: str,
    ) -> RegimeSnapshotSchema:
        volatility_pct = self._calc_volatility_pct(bars)
        trend_strength = self._calc_trend_strength(indicators)
        adx_value = indicators.adx or 0.0

        if volatility_pct >= self.config.volatility_high_pct:
            regime = RegimeType.VOLATILE
            confidence = min(volatility_pct / (self.config.volatility_high_pct * 2), 1.0)
        elif adx_value >= self.config.adx_trend_threshold:
            if trend_strength > 0:
                regime = RegimeType.TRENDING_UP
            elif trend_strength < 0:
                regime = RegimeType.TRENDING_DOWN
            else:
                regime = RegimeType.RANGING
            confidence = min(adx_value / 50.0, 1.0)
        elif adx_value <= self.config.adx_range_threshold:
            regime = RegimeType.RANGING
            confidence = 1.0 - (adx_value / self.config.adx_range_threshold)
        else:
            regime = RegimeType.UNKNOWN
            confidence = 0.3

        return RegimeSnapshotSchema(
            symbol=symbol,
            timestamp=indicators.timestamp,
            regime=regime,
            confidence=round(confidence, 4),
            adx_value=adx_value,
            volatility_pct=round(volatility_pct, 4),
            trend_strength=round(trend_strength, 4),
        )
