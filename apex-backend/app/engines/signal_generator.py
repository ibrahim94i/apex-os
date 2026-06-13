"""Signal generation orchestrator."""

from datetime import datetime, timezone

from app.config import settings
from app.services.selectivity import effective_min_confidence
from app.config.assets import get_asset
from app.config.accounts import get_balance_for_mode
from app.utils.price_zones import entry_zone_from_price
from app.logging_config import logger
from app.engines.degradation_engine import DegradationEngine
from app.engines.indicator_engine import IndicatorEngine, OHLCVBar
from app.engines.regime_engine import RegimeEngine
from app.engines.risk_calculator import RiskCalculator
from app.engines.sl_tp_engine import SLTPEngine
from app.engines.trade_level_validator import validate_trade_levels
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
        self.indicator_engine = IndicatorEngine(min_bars=60)
        self.regime_engine = RegimeEngine()
        self.sl_tp_engine = SLTPEngine()
        self.risk_calculator = RiskCalculator()
        self.degradation_engine = DegradationEngine()

    @property
    def _min_confidence(self) -> float:
        return effective_min_confidence()

    def _entry_zone(
        self, symbol: str, close: float
    ) -> tuple[float, float, float]:
        """Entry zone ±0.25% from current price; SL/TP use zone center."""
        asset = get_asset(symbol)
        decimals = asset.price_decimals if asset else 2
        return entry_zone_from_price(close, decimals=decimals)

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
        collective_confidence: float | None = None,
    ) -> tuple[TradingSignalSchema | None, str | None]:
        """
        Build a trading signal. Floor checks use collective_confidence when provided
        (agent consensus before SNR/degradation gates), while signal.confidence
        reflects the passed confidence (typically SNR-adjusted).
        """
        if direction == SignalDirection.NEUTRAL or kill_switch_active:
            return None, "neutral_direction"

        floor = min_confidence if min_confidence is not None else self._min_confidence
        floor_source = (
            collective_confidence if collective_confidence is not None else confidence
        )
        if require_min_confidence and floor_source < floor:
            return None, "confidence_below_threshold"

        zone_low, zone_high, entry_center = self._entry_zone(symbol, bars[-1].close)
        sltp = self.sl_tp_engine.calculate(
            zone_low,
            zone_high,
            direction,
            indicators,
            regime.regime,
        )

        atr = indicators.atr or (entry_center * 0.01)
        level_check = validate_trade_levels(
            direction=direction,
            entry_price=sltp.entry_price,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
            stop_loss=sltp.stop_loss,
            take_profit=sltp.take_profit,
            atr=atr,
            min_rr=settings.min_risk_reward_ratio,
        )
        if not level_check.valid:
            logger.info(
                "invalid_trade_levels",
                symbol=symbol,
                direction=direction.value,
                detail=level_check.detail,
                entry_zone_low=zone_low,
                entry_zone_high=zone_high,
                stop_loss=sltp.stop_loss,
                take_profit=sltp.take_profit,
                atr=atr,
            )
            return None, level_check.reason

        balance = account_balance if account_balance is not None else get_balance_for_mode("demo")
        calc = RiskCalculator(account_balance=balance)
        position = calc.calculate(sltp.entry_price, sltp.stop_loss, direction.value)

        signal = TradingSignalSchema(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=direction,
            confidence=confidence,
            entry_price=sltp.entry_price,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
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

        if require_min_confidence and floor_source < floor:
            return None, "confidence_below_threshold"

        return signal, None

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
        signal, _ = self.build_trading_signal(
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
