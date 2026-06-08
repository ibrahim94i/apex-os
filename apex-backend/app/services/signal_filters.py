"""High Selectivity Mode — confluence, regime, session, volatility, news filters."""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.core.redis_client import get_redis
from app.engines.indicator_engine import IndicatorEngine, OHLCVBar
from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole
from app.services.market_hours import is_gold_trading_session
from app.services.selectivity import selectivity_confidence_floor, strong_agent_bypass_threshold


NEWS_BLOCK_KEY = "apex:news_block:{symbol}"


async def set_news_block(symbol: str, minutes: int | None = None) -> None:
    window = minutes if minutes is not None else settings.news_block_window_minutes
    redis = await get_redis()
    await redis.setex(NEWS_BLOCK_KEY.format(symbol=symbol), window * 60, "1")


async def check_news_block(symbol: str) -> bool:
    redis = await get_redis()
    return bool(await redis.get(NEWS_BLOCK_KEY.format(symbol=symbol)))


def detect_high_impact_news(consensus: AgentConsensus | None) -> bool:
    """Mark news block when news agent warns of macro / volatile events."""
    if not consensus:
        return False
    for verdict in consensus.verdicts:
        if verdict.agent_id == AgentRole.NEWS:
            continue
        text = " ".join(verdict.reasoning).lower()
        high_impact = any(
            k in text
            for k in ("macro", "أخبار", "حدث", "volatile", "تذبذب", "خبر", "fomc", "nfp", "cpi")
        )
        if high_impact and verdict.direction == SignalDirection.NEUTRAL and verdict.confidence >= 0.6:
            return True
        if high_impact and verdict.confidence >= 0.7:
            return True
    return False


def check_confluence(
    direction: SignalDirection,
    indicators: IndicatorSnapshotSchema,
    *,
    skip_rsi: bool = False,
) -> tuple[bool, str | None]:
    if direction == SignalDirection.NEUTRAL:
        return False, "neutral_direction"

    if indicators.ema_50 is None or indicators.ema_200 is None:
        return False, "missing_ema50_ema200"

    if direction == SignalDirection.LONG and indicators.ema_50 <= indicators.ema_200:
        return False, "ema_confluence_long"
    if direction == SignalDirection.SHORT and indicators.ema_50 >= indicators.ema_200:
        return False, "ema_confluence_short"

    if not skip_rsi:
        if indicators.rsi is None:
            return False, "missing_rsi"
        if not (settings.rsi_filter_min <= indicators.rsi <= settings.rsi_filter_max):
            return False, "rsi_out_of_range"

    if indicators.macd is None or indicators.macd_signal is None:
        return False, "missing_macd"
    if direction == SignalDirection.LONG and indicators.macd <= indicators.macd_signal:
        return False, "macd_confluence_long"
    if direction == SignalDirection.SHORT and indicators.macd >= indicators.macd_signal:
        return False, "macd_confluence_short"

    return True, None


def get_agent_confidences(consensus: AgentConsensus | None) -> tuple[float | None, float | None]:
    if not consensus:
        return None, None
    market: float | None = None
    risk: float | None = None
    for verdict in consensus.verdicts:
        if verdict.agent_id == AgentRole.MARKET_ANALYST:
            market = verdict.confidence
        elif verdict.agent_id == AgentRole.RISK:
            risk = verdict.confidence
    return market, risk


def should_bypass_all_selectivity_filters(
    consensus: AgentConsensus | None,
    regime: RegimeSnapshotSchema | None,
) -> bool:
    """
    Collective >= 75% with clear trending regime → skip RSI, ATR, MACD, SNR, regime filters.
    Safety Gate, Economic Calendar, and Kill Switch remain enforced in the pipeline.
    """
    if consensus is None or regime is None:
        return False
    if consensus.final_direction == SignalDirection.NEUTRAL:
        return False
    if consensus.final_confidence < strong_agent_bypass_threshold():
        return False
    return regime.regime in (RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN)


def should_bypass_rsi_atr_filters(
    direction: SignalDirection,
    signal_confidence: float,
    consensus: AgentConsensus | None = None,
    regime: RegimeSnapshotSchema | None = None,
) -> bool:
    """Strong trend bypass only — 70–75% tier applies all technical filters."""
    return should_bypass_all_selectivity_filters(consensus, regime)


def should_bypass_technical_filters(
    direction: SignalDirection,
    confidence: float,
    consensus: AgentConsensus | None = None,
    regime: RegimeSnapshotSchema | None = None,
) -> bool:
    """Alias for full selectivity bypass under strong trending consensus."""
    return should_bypass_all_selectivity_filters(consensus, regime)


def passes_selectivity_confidence_floor(
    signal_confidence: float,
    consensus: AgentConsensus | None = None,
) -> bool:
    """Allow degraded signal confidence when collective consensus still meets floor."""
    floor = selectivity_confidence_floor()
    if signal_confidence >= floor:
        return True
    if consensus is not None and consensus.final_confidence >= floor:
        return True
    return False


def check_regime_filter(
    direction: SignalDirection,
    regime: RegimeSnapshotSchema,
    *,
    skip_adx: bool = False,
    symbol: str | None = None,
) -> tuple[bool, str | None]:
    r = regime.regime

    if r in (RegimeType.RANGING, RegimeType.UNKNOWN):
        return False, f"regime_blocked_{r.value.lower()}"

    if not skip_adx:
        if regime.adx_value is not None and regime.adx_value < 15:
            return False, "regime_choppy"
    if (
        regime.volatility_pct is not None
        and regime.volatility_pct < 0.3
        and symbol != "XAUUSD"
    ):
        return False, "regime_low_liquidity"

    if r in (RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN):
        return True, None

    if r == RegimeType.VOLATILE:
        trend_clear = regime.trend_strength is not None and abs(regime.trend_strength) >= 0.25
        if skip_adx:
            if trend_clear:
                return True, None
        else:
            adx_ok = (
                regime.adx_value is not None
                and regime.adx_value >= settings.adx_trend_clear_threshold
            )
            if trend_clear and adx_ok:
                return True, None
        return False, "regime_volatile_no_clear_trend"

    return False, "regime_blocked"


def check_atr_volatility(
    indicators: IndicatorSnapshotSchema,
    bars: list[OHLCVBar],
) -> tuple[bool, str | None]:
    if indicators.atr is None:
        return False, "missing_atr"

    atr_avg = indicators.atr_avg_20
    if atr_avg is None and len(bars) >= 20:
        engine = IndicatorEngine(min_bars=20)
        df_bars = bars
        atr_avg = _compute_atr_avg_20(engine, df_bars)

    if atr_avg is None or atr_avg <= 0:
        return True, None

    if indicators.atr < atr_avg * settings.atr_volatility_floor_ratio:
        return False, "atr_too_low"

    return True, None


def _compute_atr_avg_20(engine: IndicatorEngine, bars: list[OHLCVBar]) -> float | None:
    import pandas as pd

    if len(bars) < 20:
        return None
    df = engine._to_dataframe(bars)
    atr_series = engine._atr(df["high"], df["low"], df["close"], 14)
    tail = atr_series.dropna().tail(20)
    if tail.empty:
        return None
    return float(tail.mean())


async def apply_high_selectivity_filters(
    symbol: str,
    direction: SignalDirection,
    confidence: float,
    indicators: IndicatorSnapshotSchema,
    regime: RegimeSnapshotSchema,
    bars: list[OHLCVBar],
    consensus: AgentConsensus | None = None,
) -> tuple[bool, str | None]:
    """Return (allowed, rejection_reason). False = WAIT."""
    if not passes_selectivity_confidence_floor(confidence, consensus):
        return False, "confidence_below_threshold"

    if should_bypass_all_selectivity_filters(consensus, regime):
        return True, None

    ok, reason = check_confluence(direction, indicators, skip_rsi=False)
    if not ok:
        return False, reason

    ok, reason = check_regime_filter(direction, regime, skip_adx=False, symbol=symbol)
    if not ok:
        return False, reason

    if symbol == "XAUUSD" and not is_gold_trading_session():
        return False, "gold_session_closed"

    ok, reason = check_atr_volatility(indicators, bars)
    if not ok:
        return False, reason

    if await check_news_block(symbol):
        return False, "high_impact_news_window"

    if detect_high_impact_news(consensus):
        await set_news_block(symbol)
        return False, "high_impact_news_detected"

    return True, None
