"""Builds MarketSnapshot from live pipeline context."""

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.logging_config import logger
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatusSchema, RegimeSnapshotSchema
from app.schemas.agent import CandlestickPatternSchema, EconomicEventSchema, MarketSnapshot
from app.schemas.snr import SNRSnapshotSchema
from app.services.account_service import account_service
from app.services.finnhub_calendar import fetch_upcoming_high_impact_events
from app.services.feed_freshness import is_feed_poll_stale
from app.services.memory_engine import memory_engine
from app.services.news_aggregator import fetch_news_for_symbol


def redis_snapshot_matches_symbol(symbol: str, data: dict[str, Any] | None) -> bool:
    """True when cached Redis payload belongs to this symbol (or has no symbol field)."""
    if not data:
        return False
    stored = data.get("symbol")
    return not stored or stored == symbol


def bind_indicator_regime_to_symbol(
    symbol: str,
    indicators: IndicatorSnapshotSchema,
    regime: RegimeSnapshotSchema,
) -> tuple[IndicatorSnapshotSchema, RegimeSnapshotSchema]:
    """Ensure nested snapshots cannot leak data from another asset."""
    if indicators.symbol != symbol:
        logger.warning(
            "snapshot_indicators_symbol_mismatch",
            requested=symbol,
            stored=indicators.symbol,
        )
    if regime.symbol != symbol:
        logger.warning(
            "snapshot_regime_symbol_mismatch",
            requested=symbol,
            stored=regime.symbol,
        )
    return (
        indicators.model_copy(update={"symbol": symbol}),
        regime.model_copy(update={"symbol": symbol}),
    )


async def build_market_snapshot(
    symbol: str,
    price: float,
    indicators: IndicatorSnapshotSchema,
    regime: RegimeSnapshotSchema,
    kill_switch: KillSwitchStatusSchema,
    candlestick_patterns: list[CandlestickPatternSchema] | None = None,
    upcoming_events: list[EconomicEventSchema] | None = None,
    snr: SNRSnapshotSchema | None = None,
    eval_timestamp: datetime | None = None,
) -> MarketSnapshot:
    indicators, regime = bind_indicator_regime_to_symbol(symbol, indicators, regime)
    feed_stale = await _is_feed_stale(symbol)
    patterns = await memory_engine.get_top_patterns(symbol)

    if candlestick_patterns is None:
        from app.engines.candlestick_engine import candlestick_engine
        from app.services.pipeline import fetch_decision_bars

        bars = await fetch_decision_bars(symbol)
        candlestick_patterns = candlestick_engine.detect(bars)

    if snr is None:
        from app.services.pipeline import compute_snr_for_symbol

        snr = await compute_snr_for_symbol(symbol)

    balance = await account_service.get_balance()
    news_headlines = await fetch_news_for_symbol(symbol)
    if upcoming_events is None:
        upcoming_events = await fetch_upcoming_high_impact_events()

    snapshot_time = eval_timestamp or datetime.now(timezone.utc)
    if snapshot_time.tzinfo is None:
        snapshot_time = snapshot_time.replace(tzinfo=timezone.utc)

    return MarketSnapshot(
        symbol=symbol,
        timestamp=snapshot_time,
        price=price,
        indicators=indicators,
        regime=regime,
        kill_switch=kill_switch,
        account_balance=balance,
        max_risk_pct=settings.max_risk_per_trade_pct,
        max_drawdown_pct=settings.max_drawdown_pct,
        daily_loss_pct=kill_switch.daily_loss_pct or 0.0,
        consecutive_losses=kill_switch.consecutive_losses or 0,
        feed_stale=feed_stale,
        memory_patterns=patterns,
        candlestick_patterns=candlestick_patterns,
        news_headlines=news_headlines,
        upcoming_events=upcoming_events,
        snr=snr,
    )


async def _is_feed_stale(symbol: str) -> bool:
    try:
        return await is_feed_poll_stale(symbol)
    except Exception:
        return True
