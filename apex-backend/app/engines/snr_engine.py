"""Support & Resistance engine — pivot highs/lows on H1 OHLCV (Core, not Agent)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.engines.indicator_engine import OHLCVBar
from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRSnapshotSchema

PIVOT_STRENGTH = 2
MAX_LOOKBACK_BARS = 500
NEAR_LEVEL_PCT = 0.5
PENALTY = 0.15
BREAKOUT_BONUS = 0.10
LEVEL_MERGE_TOLERANCE_PCT = 0.05


@dataclass
class SNRAdjustmentResult:
    confidence: float
    reasons: list[str]


class SNREngine:
    """Compute S1–S3 / R1–R3 from pivot lows/highs and adjust signal confidence."""

    def compute(
        self,
        bars: list[OHLCVBar],
        symbol: str,
        *,
        at: datetime | None = None,
    ) -> SNRSnapshotSchema | None:
        if len(bars) < PIVOT_STRENGTH * 2 + 3:
            return None

        window = bars[-MAX_LOOKBACK_BARS:]
        price = window[-1].close
        pivot_highs = self._find_pivot_highs(window)
        pivot_lows = self._find_pivot_lows(window)

        resistances = self._select_levels(
            [level for _, level in pivot_highs if level > price],
            ascending=True,
            count=3,
        )
        supports = self._select_levels(
            [level for _, level in pivot_lows if level < price],
            ascending=False,
            count=3,
        )

        dist_support = self._distance_pct(price, supports[0], below=True) if supports[0] else None
        dist_resistance = (
            self._distance_pct(price, resistances[0], below=False) if resistances[0] else None
        )

        return SNRSnapshotSchema(
            symbol=symbol,
            timestamp=at or window[-1].timestamp,
            price=price,
            support_1=supports[0],
            support_2=supports[1],
            support_3=supports[2],
            resistance_1=resistances[0],
            resistance_2=resistances[1],
            resistance_3=resistances[2],
            distance_to_support_pct=dist_support,
            distance_to_resistance_pct=dist_resistance,
            pivot_high_count=len(pivot_highs),
            pivot_low_count=len(pivot_lows),
        )

    def adjust_confidence(
        self,
        *,
        price: float,
        prev_close: float,
        direction: SignalDirection,
        confidence: float,
        snr: SNRSnapshotSchema,
    ) -> SNRAdjustmentResult:
        if direction == SignalDirection.NEUTRAL:
            return SNRAdjustmentResult(confidence=confidence, reasons=[])

        adjusted = confidence
        reasons: list[str] = []

        if direction == SignalDirection.LONG:
            if snr.resistance_1 is not None:
                dist_r = self._distance_pct(price, snr.resistance_1, below=False)
                if dist_r is not None and dist_r <= NEAR_LEVEL_PCT:
                    adjusted -= PENALTY
                    reasons.append("snr_near_resistance_long_penalty")
                if prev_close <= snr.resistance_1 < price:
                    adjusted += BREAKOUT_BONUS
                    reasons.append("snr_bullish_breakout")

        elif direction == SignalDirection.SHORT:
            if snr.support_1 is not None:
                dist_s = self._distance_pct(price, snr.support_1, below=True)
                if dist_s is not None and dist_s <= NEAR_LEVEL_PCT:
                    adjusted -= PENALTY
                    reasons.append("snr_near_support_short_penalty")
                if prev_close >= snr.support_1 > price:
                    adjusted += BREAKOUT_BONUS
                    reasons.append("snr_bearish_breakout")

        adjusted = round(min(max(adjusted, 0.0), 1.0), 4)
        return SNRAdjustmentResult(confidence=adjusted, reasons=reasons)

    @staticmethod
    def _find_pivot_highs(bars: list[OHLCVBar]) -> list[tuple[int, float]]:
        pivots: list[tuple[int, float]] = []
        n = len(bars)
        for i in range(PIVOT_STRENGTH, n - PIVOT_STRENGTH):
            high = bars[i].high
            if all(high > bars[i - j].high and high > bars[i + j].high for j in range(1, PIVOT_STRENGTH + 1)):
                pivots.append((i, high))
        return pivots

    @staticmethod
    def _find_pivot_lows(bars: list[OHLCVBar]) -> list[tuple[int, float]]:
        pivots: list[tuple[int, float]] = []
        n = len(bars)
        for i in range(PIVOT_STRENGTH, n - PIVOT_STRENGTH):
            low = bars[i].low
            if all(low < bars[i - j].low and low < bars[i + j].low for j in range(1, PIVOT_STRENGTH + 1)):
                pivots.append((i, low))
        return pivots

    @staticmethod
    def _merge_close_levels(levels: list[float]) -> list[float]:
        if not levels:
            return []
        sorted_levels = sorted(levels)
        merged: list[float] = []
        for level in sorted_levels:
            if not merged:
                merged.append(level)
                continue
            ref = merged[-1]
            if ref > 0 and abs(level - ref) / ref * 100 <= LEVEL_MERGE_TOLERANCE_PCT:
                merged[-1] = (ref + level) / 2
            else:
                merged.append(level)
        return merged

    def _select_levels(
        self,
        levels: list[float],
        *,
        ascending: bool,
        count: int,
    ) -> list[float | None]:
        unique = self._merge_close_levels(levels)
        ordered = sorted(unique, reverse=not ascending)
        out: list[float | None] = []
        for i in range(count):
            out.append(ordered[i] if i < len(ordered) else None)
        return out

    @staticmethod
    def _distance_pct(price: float, level: float, *, below: bool) -> float | None:
        if price <= 0 or level <= 0:
            return None
        if below:
            if level >= price:
                return None
            return (price - level) / price * 100
        if level <= price:
            return None
        return (level - price) / price * 100


snr_engine = SNREngine()
