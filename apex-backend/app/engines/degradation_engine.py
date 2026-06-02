"""Confidence degradation engine — reduces signal confidence under adverse conditions."""

from dataclasses import dataclass

from app.config import settings
from app.schemas import (
    IndicatorSnapshotSchema,
    KillSwitchStatus,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
    RegimeType,
    SignalDirection,
    TradingSignalSchema,
)


@dataclass
class DegradationResult:
    confidence: float
    degraded: bool
    reason: str | None = None


class DegradationEngine:
    DEGRADATION_FACTORS = {
        "kill_switch_active": 0.0,
        "volatile_regime": 0.7,
        "unknown_regime": 0.5,
        "ranging_regime": 0.8,
        "low_regime_confidence": 0.6,
        "rsi_extreme": 0.75,
        "macd_divergence": 0.8,
        "feed_stale": 0.0,
    }

    def _check_rsi_extreme(self, indicators: IndicatorSnapshotSchema, direction: SignalDirection) -> bool:
        if indicators.rsi is None:
            return False
        if direction == SignalDirection.LONG and indicators.rsi > 75:
            return True
        if direction == SignalDirection.SHORT and indicators.rsi < 25:
            return True
        return False

    def _check_macd_divergence(
        self, indicators: IndicatorSnapshotSchema, direction: SignalDirection
    ) -> bool:
        if indicators.macd is None or indicators.macd_signal is None:
            return False
        if direction == SignalDirection.LONG and indicators.macd < indicators.macd_signal:
            return True
        if direction == SignalDirection.SHORT and indicators.macd > indicators.macd_signal:
            return True
        return False

    def degrade(
        self,
        base_confidence: float,
        direction: SignalDirection,
        regime: RegimeSnapshotSchema,
        indicators: IndicatorSnapshotSchema,
        kill_switch: KillSwitchStatusSchema,
        feed_stale: bool = False,
    ) -> DegradationResult:
        confidence = base_confidence
        reasons: list[str] = []

        if kill_switch.status == KillSwitchStatus.ACTIVE:
            confidence *= self.DEGRADATION_FACTORS["kill_switch_active"]
            reasons.append("Kill switch active")

        if feed_stale:
            confidence *= self.DEGRADATION_FACTORS["feed_stale"]
            reasons.append(f"Feed stale > {settings.feed_staleness_limit_seconds}s")

        if regime.regime == RegimeType.VOLATILE:
            confidence *= self.DEGRADATION_FACTORS["volatile_regime"]
            reasons.append("Volatile regime")
        elif regime.regime == RegimeType.UNKNOWN:
            confidence *= self.DEGRADATION_FACTORS["unknown_regime"]
            reasons.append("Unknown regime")
        elif regime.regime == RegimeType.RANGING:
            confidence *= self.DEGRADATION_FACTORS["ranging_regime"]
            reasons.append("Ranging regime")

        if regime.confidence < 0.5:
            confidence *= self.DEGRADATION_FACTORS["low_regime_confidence"]
            reasons.append("Low regime confidence")

        if self._check_rsi_extreme(indicators, direction):
            confidence *= self.DEGRADATION_FACTORS["rsi_extreme"]
            reasons.append("RSI extreme")

        if self._check_macd_divergence(indicators, direction):
            confidence *= self.DEGRADATION_FACTORS["macd_divergence"]
            reasons.append("MACD divergence")

        confidence = round(min(max(confidence, 0.0), 1.0), 4)
        degraded = confidence < base_confidence

        return DegradationResult(
            confidence=confidence,
            degraded=degraded,
            reason="; ".join(reasons) if reasons else None,
        )

    def apply_to_signal(
        self,
        signal: TradingSignalSchema,
        regime: RegimeSnapshotSchema,
        indicators: IndicatorSnapshotSchema,
        kill_switch: KillSwitchStatusSchema,
        feed_stale: bool = False,
    ) -> TradingSignalSchema:
        result = self.degrade(
            signal.confidence,
            signal.direction,
            regime,
            indicators,
            kill_switch,
            feed_stale,
        )
        signal.confidence = result.confidence
        signal.degraded = result.degraded
        signal.degradation_reason = result.reason
        signal.kill_switch_active = kill_switch.status == KillSwitchStatus.ACTIVE
        return signal
