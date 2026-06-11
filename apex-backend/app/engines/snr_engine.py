"""Support & Resistance engine — pivot highs/lows on H1 OHLCV (Core, not Agent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.engines.indicator_engine import OHLCVBar
from app.logging_config import logger
from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRLevelZone, SNRSnapshotSchema
from app.utils.price_zones import level_zone_bounds, price_in_zone

PIVOT_STRENGTH = 2
MAX_LOOKBACK_BARS = 500
NEAR_LEVEL_PCT = 0.5
PENALTY = 0.15
BREAKOUT_BONUS = 0.10
LEVEL_MERGE_TOLERANCE_PCT = 0.05

SNRCategory = Literal["breakout", "rejection", "snr_zone"]


@dataclass
class SNREvaluationResult:
    confidence: float
    block_signal: bool = False
    block_reason: str | None = None
    reasons: list[str] = field(default_factory=list)
    category: SNRCategory | None = None
    explain_ar: str | None = None


class SNREngine:
    """Compute S1–S3 / R1–R3 from pivot lows/highs and evaluate signals."""

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

        res_levels = [level for _, level in pivot_highs if level > price]
        sup_levels = [level for _, level in pivot_lows if level < price]

        if not res_levels:
            res_levels = self._fallback_levels_above(window, price)
        if not sup_levels:
            sup_levels = self._fallback_levels_below(window, price)

        if not res_levels and not sup_levels:
            logger.warning(
                "snr_no_levels",
                symbol=symbol,
                bars=len(window),
                price=price,
                pivot_highs=len(pivot_highs),
                pivot_lows=len(pivot_lows),
            )

        resistances = self._select_levels(res_levels, ascending=True, count=3)
        supports = self._select_levels(sup_levels, ascending=False, count=3)

        dist_support = self._distance_pct(price, supports[0], below=True) if supports[0] else None
        dist_resistance = (
            self._distance_pct(price, resistances[0], below=False) if resistances[0] else None
        )

        s1, s2, s3 = supports
        r1, r2, r3 = resistances

        return SNRSnapshotSchema(
            symbol=symbol,
            timestamp=at or window[-1].timestamp,
            price=price,
            support_1=s1,
            support_2=s2,
            support_3=s3,
            resistance_1=r1,
            resistance_2=r2,
            resistance_3=r3,
            support_1_zone=self._make_zone(s1),
            support_2_zone=self._make_zone(s2),
            support_3_zone=self._make_zone(s3),
            resistance_1_zone=self._make_zone(r1),
            resistance_2_zone=self._make_zone(r2),
            resistance_3_zone=self._make_zone(r3),
            distance_to_support_pct=dist_support,
            distance_to_resistance_pct=dist_resistance,
            pivot_high_count=len(pivot_highs),
            pivot_low_count=len(pivot_lows),
        )

    def evaluate_signal(
        self,
        *,
        bars: list[OHLCVBar],
        direction: SignalDirection,
        confidence: float,
        snr: SNRSnapshotSchema,
    ) -> SNREvaluationResult:
        """Level zones (±0.25%), confirmed breakouts, rejection penalties."""
        if direction == SignalDirection.NEUTRAL or not bars:
            return SNREvaluationResult(confidence=confidence)

        price = bars[-1].close
        in_zone, zone_reason, zone_label = self._price_in_level_zone(price, snr)
        if in_zone:
            explain = self._zone_explain_ar(zone_label, zone_reason, snr, price)
            return SNREvaluationResult(
                confidence=confidence,
                block_signal=True,
                block_reason=zone_reason,
                reasons=[zone_reason or "snr_in_level_zone"],
                category="snr_zone",
                explain_ar=explain,
            )

        adjusted = confidence
        reasons: list[str] = []
        category: SNRCategory | None = None
        explain_ar: str | None = None

        if direction == SignalDirection.LONG:
            if snr.resistance_1 is not None:
                _, r1_high = level_zone_bounds(snr.resistance_1)
                if self._confirmed_bullish_breakout(bars, r1_high):
                    adjusted += BREAKOUT_BONUS
                    reasons.append("snr_bullish_breakout")
                    category = "breakout"
                    explain_ar = (
                        f"شراء — Bullish Breakout فوق منطقة R1 "
                        f"({snr.resistance_1:.2f} ±0.25%)"
                    )
                else:
                    dist_r = self._distance_pct(price, snr.resistance_1, below=False)
                    if dist_r is not None and dist_r <= NEAR_LEVEL_PCT:
                        adjusted -= PENALTY
                        reasons.append("snr_near_resistance_long_penalty")
                        category = "rejection"
                        explain_ar = f"شراء — Rejection عند R1 ({snr.resistance_1:.2f})"

        elif direction == SignalDirection.SHORT:
            if snr.support_1 is not None:
                s1_low, _ = level_zone_bounds(snr.support_1)
                if self._confirmed_bearish_breakout(bars, s1_low):
                    adjusted += BREAKOUT_BONUS
                    reasons.append("snr_bearish_breakout")
                    category = "breakout"
                    explain_ar = (
                        f"بيع — Bearish Breakout تحت منطقة S1 "
                        f"({snr.support_1:.2f} ±0.25%)"
                    )
                else:
                    dist_s = self._distance_pct(price, snr.support_1, below=True)
                    if dist_s is not None and dist_s <= NEAR_LEVEL_PCT:
                        adjusted -= PENALTY
                        reasons.append("snr_near_support_short_penalty")
                        category = "rejection"
                        explain_ar = f"بيع — Rejection عند S1 ({snr.support_1:.2f})"

        adjusted = round(min(max(adjusted, 0.0), 1.0), 4)
        return SNREvaluationResult(
            confidence=adjusted,
            reasons=reasons,
            category=category,
            explain_ar=explain_ar,
        )

    def adjust_confidence(
        self,
        *,
        price: float,
        prev_close: float,
        direction: SignalDirection,
        confidence: float,
        snr: SNRSnapshotSchema,
        bars: list[OHLCVBar] | None = None,
    ) -> SNREvaluationResult:
        """Backward-compatible wrapper — prefer evaluate_signal with full bar history."""
        if bars and len(bars) >= 1:
            merged = list(bars[:-1]) + [
                OHLCVBar(
                    timestamp=bars[-1].timestamp,
                    open=bars[-1].open,
                    high=bars[-1].high,
                    low=bars[-1].low,
                    close=price,
                    volume=bars[-1].volume,
                )
            ]
            if len(merged) >= 2:
                return self.evaluate_signal(
                    bars=merged,
                    direction=direction,
                    confidence=confidence,
                    snr=snr,
                )
        synthetic = [
            OHLCVBar(
                timestamp=snr.timestamp,
                open=prev_close,
                high=max(prev_close, price),
                low=min(prev_close, price),
                close=prev_close,
                volume=0.0,
            ),
            OHLCVBar(
                timestamp=snr.timestamp,
                open=prev_close,
                high=max(prev_close, price),
                low=min(prev_close, price),
                close=price,
                volume=0.0,
            ),
        ]
        return self.evaluate_signal(
            bars=synthetic,
            direction=direction,
            confidence=confidence,
            snr=snr,
        )

    @staticmethod
    def _make_zone(level: float | None) -> SNRLevelZone | None:
        if level is None:
            return None
        low, high = level_zone_bounds(level)
        return SNRLevelZone(level=level, low=low, high=high)

    @staticmethod
    def _price_in_level_zone(
        price: float,
        snr: SNRSnapshotSchema,
    ) -> tuple[bool, str | None, str | None]:
        checks: list[tuple[str, SNRLevelZone | None, str]] = [
            ("S1", snr.support_1_zone, "snr_in_s1_zone"),
            ("S2", snr.support_2_zone, "snr_in_s2_zone"),
            ("S3", snr.support_3_zone, "snr_in_s3_zone"),
            ("R1", snr.resistance_1_zone, "snr_in_r1_zone"),
            ("R2", snr.resistance_2_zone, "snr_in_r2_zone"),
            ("R3", snr.resistance_3_zone, "snr_in_r3_zone"),
        ]
        for label, zone, reason in checks:
            if zone and price_in_zone(price, zone.low, zone.high):
                return True, reason, label
        return False, None, None

    @staticmethod
    def _confirmed_bullish_breakout(bars: list[OHLCVBar], zone_high: float) -> bool:
        if len(bars) < 2 or zone_high <= 0:
            return False
        breakout = bars[-2]
        confirm = bars[-1]
        if breakout.close <= zone_high:
            return False
        if confirm.close <= zone_high:
            return False
        return confirm.close >= breakout.close

    @staticmethod
    def _confirmed_bearish_breakout(bars: list[OHLCVBar], zone_low: float) -> bool:
        if len(bars) < 2 or zone_low <= 0:
            return False
        breakout = bars[-2]
        confirm = bars[-1]
        if breakout.close >= zone_low:
            return False
        if confirm.close >= zone_low:
            return False
        return confirm.close <= breakout.close

    @staticmethod
    def _zone_explain_ar(
        label: str | None,
        reason: str | None,
        snr: SNRSnapshotSchema,
        price: float,
    ) -> str:
        zone_map = {
            "S1": snr.support_1_zone,
            "S2": snr.support_2_zone,
            "S3": snr.support_3_zone,
            "R1": snr.resistance_1_zone,
            "R2": snr.resistance_2_zone,
            "R3": snr.resistance_3_zone,
        }
        zone = zone_map.get(label or "")
        if zone:
            return (
                f"انتظار — السعر {price:.2f} داخل منطقة {label} "
                f"({zone.low:.2f} – {zone.high:.2f})"
            )
        return "انتظار — السعر داخل منطقة SNR (±0.25%)"

    @staticmethod
    def _fallback_levels_above(bars: list[OHLCVBar], price: float) -> list[float]:
        """Use distinct bar highs above price when pivot detection finds none."""
        return sorted({b.high for b in bars if b.high > price})

    @staticmethod
    def _fallback_levels_below(bars: list[OHLCVBar], price: float) -> list[float]:
        """Use distinct bar lows below price when pivot detection finds none."""
        return sorted({b.low for b in bars if b.low < price}, reverse=True)

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
