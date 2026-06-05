"""Signal generation orchestrator."""

from datetime import datetime, timezone

from app.config import settings
from app.services.selectivity import effective_min_confidence
from app.config.assets import get_asset
from app.config.accounts import get_balance_for_mode
from app.engines.degradation_engine import DegradationEngine
from app.engines.indicator_engine import IndicatorEngine, OHLCVBar
from app.engines.regime_engine import RegimeEngine
from app.engines.risk_calculator import RiskCalculator
from app.engines.sl_tp_engine import SLTPEngine
from app.schemas import (
    IndicatorSnapshotSchema,
    KillSwitchStatus,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
    RegimeType,
    SignalDirection,
    TradingSignalSchema,
)


class SignalGenerator:
    def __init__(self) -> None:
        self.indicator_engine = IndicatorEngine()
        self.regime_engine = RegimeEngine()
        self.sl_tp_engine = SLTPEngine()
        self.risk_calculator = RiskCalculator()
        self.degradation_engine = DegradationEngine()

    @property
    def _min_confidence(self) -> float:
        return effective_min_confidence()

    def _entry_price(
        self, symbol: str, close: float, direction: SignalDirection
    ) -> float:
        """Apply half-spread to simulate bid/ask on entry."""
        asset = get_asset(symbol)
        spread = asset.default_spread if asset and asset.default_spread else 0.0
        decimals = asset.price_decimals if asset else 2
        if direction == SignalDirection.LONG:
            return round(close + spread / 2, decimals)
        if direction == SignalDirection.SHORT:
            return round(close - spread / 2, decimals)
        return close

    def _determine_direction(
        self,
        indicators: IndicatorSnapshotSchema,
        regime: RegimeSnapshotSchema,
    ) -> tuple[SignalDirection, float]:
        score = 0.0
        factors = 0

        if indicators.rsi is not None:
            factors += 1
            if indicators.rsi < 35:
                score += 1.0
            elif indicators.rsi > 65:
                score -= 1.0

        if indicators.macd is not None and indicators.macd_signal is not None:
            factors += 1
            if indicators.macd > indicators.macd_signal:
                score += 1.0
            else:
                score -= 1.0

        if indicators.ema_9 is not None and indicators.ema_21 is not None:
            factors += 1
            if indicators.ema_9 > indicators.ema_21:
                score += 1.0
            else:
                score -= 1.0

        if regime.regime == RegimeType.TRENDING_UP:
            score += 0.5
        elif regime.regime == RegimeType.TRENDING_DOWN:
            score -= 0.5

        if factors == 0:
            return SignalDirection.NEUTRAL, 0.0

        normalized = score / (factors + 0.5)
        confidence = min(abs(normalized), 1.0)

        if normalized > 0.3:
            return SignalDirection.LONG, confidence
        if normalized < -0.3:
            return SignalDirection.SHORT, confidence
        return SignalDirection.NEUTRAL, confidence * 0.5

    def analyze(
        self,
        bars: list[OHLCVBar],
        symbol: str,
    ) -> tuple[IndicatorSnapshotSchema | None, RegimeSnapshotSchema | None]:
        indicators = self.indicator_engine.compute(bars, symbol)
        if indicators is None:
            return None, None
        regime = self.regime_engine.classify(bars, indicators, symbol)
        return indicators, regime

    def build_trading_signal(
        self,
        bars: list[OHLCVBar],
        symbol: str,
        direction: SignalDirection,
        confidence: float,
        indicators: IndicatorSnapshotSchema,
        regime: RegimeSnapshotSchema,
        kill_switch_active: bool = False,
        feed_stale: bool = False,
        account_balance: float | None = None,
        *,
        require_min_confidence: bool = True,
        min_confidence: float | None = None,
    ) -> TradingSignalSchema | None:
        if direction == SignalDirection.NEUTRAL or kill_switch_active:
            return None

        floor = min_confidence if min_confidence is not None else self._min_confidence
        if require_min_confidence and confidence < floor:
            return None

        entry_price = self._entry_price(symbol, bars[-1].close, direction)
        sltp = self.sl_tp_engine.calculate(entry_price, direction, indicators, regime.regime)
        if sltp.risk_reward_ratio < settings.min_risk_reward_ratio:
            return None

        balance = account_balance if account_balance is not None else get_balance_for_mode("demo")
        calc = RiskCalculator(account_balance=balance)
        position = calc.calculate(sltp.entry_price, sltp.stop_loss, direction.value)

        signal = TradingSignalSchema(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=direction,
            confidence=confidence,
            entry_price=sltp.entry_price,
            stop_loss=sltp.stop_loss,
            take_profit=sltp.take_profit,
            position_size=position.position_size,
            regime=regime.regime,
        )

        ks_schema = KillSwitchStatusSchema(
            status=KillSwitchStatus.ACTIVE if kill_switch_active else KillSwitchStatus.INACTIVE,
        )
        signal = self.degradation_engine.apply_to_signal(
            signal, regime, indicators, ks_schema, feed_stale
        )

        if require_min_confidence and signal.confidence < floor:
            return None

        return signal

    def generate(
        self,
        bars: list[OHLCVBar],
        symbol: str,
        kill_switch_active: bool = False,
        feed_stale: bool = False,
    ) -> tuple[IndicatorSnapshotSchema | None, RegimeSnapshotSchema | None, TradingSignalSchema | None]:
        indicators, regime = self.analyze(bars, symbol)
        if indicators is None or regime is None:
            return None, None, None

        direction, confidence = self._determine_direction(indicators, regime)
        signal = self.build_trading_signal(
            bars,
            symbol,
            direction,
            confidence,
            indicators,
            regime,
            kill_switch_active=kill_switch_active,
            feed_stale=feed_stale,
            require_min_confidence=False,
        )
        return indicators, regime, signal
