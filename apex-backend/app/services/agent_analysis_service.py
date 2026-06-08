"""Run agent consensus from cached market data when the pipeline has not yet."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.agents.orchestrator import agent_orchestrator
from app.config import settings
from app.core.cache import (
    get_agent_consensus,
    get_latest_indicators,
    get_latest_price,
    get_latest_regime,
    set_agent_consensus,
    set_latest_indicators,
    set_latest_regime,
)
from app.database import AsyncSessionLocal
from app.engines.indicator_engine import IndicatorEngine
from app.engines.signal_generator import SignalGenerator
from app.engines.kill_switch import kill_switch
from app.logging_config import logger
from app.schemas import (
    AgentConsensus,
    IndicatorSnapshotSchema,
    RegimeSnapshotSchema,
)
from app.services.market_hours import is_market_open
from app.services.feed_freshness import is_feed_poll_stale
from app.services.feed_health_service import recover_feed
from app.services.market_data_store import (
    fetch_bars_from_db,
    get_latest_price_from_db,
    get_latest_regime_from_db,
)
from app.services.market_snapshot import (
    bind_indicator_regime_to_symbol,
    build_market_snapshot,
    redis_snapshot_matches_symbol,
)
from app.services.pipeline import seed_bars_to_buffer, process_bar
from app.services.signal_rejection_i18n import rejection_reason_ar
from app.websocket.manager import broadcaster

_signal_generator = SignalGenerator()
_MIN_INDICATOR_BARS = IndicatorEngine().min_bars
_DB_BAR_LIMIT = 500
_agent_analysis_lock = asyncio.Lock()
_last_agent_run_finished_at: float = 0.0


async def _wait_agent_run_slot() -> None:
    """Gap between serialized agent runs to respect LLM rate limits."""
    global _last_agent_run_finished_at
    gap = settings.llm_min_request_interval_seconds
    wait = gap - (time.monotonic() - _last_agent_run_finished_at)
    if wait > 0:
        await asyncio.sleep(wait)


async def _recompute_market_metrics(symbol: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Rebuild indicators/regime from DB OHLCV when Redis cache is empty."""
    bars = await fetch_bars_from_db(symbol, _DB_BAR_LIMIT)
    if len(bars) < _MIN_INDICATOR_BARS:
        logger.warning(
            "agent_analysis_insufficient_bars",
            symbol=symbol,
            bars=len(bars),
            required=_MIN_INDICATOR_BARS,
        )
        return None, None

    from app.services.pipeline import _bar_buffer

    _bar_buffer[symbol] = []
    seed_bars_to_buffer(bars)
    buffer = _bar_buffer.get(symbol, [])
    indicators, regime = _signal_generator.analyze(buffer, symbol)
    if not indicators or not regime:
        return None, None

    ind_data = indicators.model_dump(mode="json")
    reg_data = regime.model_dump(mode="json")
    await set_latest_indicators(symbol, ind_data)
    await set_latest_regime(symbol, reg_data)
    return ind_data, reg_data


async def _load_market_context(
    symbol: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    price_data = await get_latest_price(symbol)
    if not price_data:
        price_data = await get_latest_price_from_db(symbol)

    regime_data = await get_latest_regime(symbol)
    if not regime_data:
        regime_data = await get_latest_regime_from_db(symbol)

    ind_data = await get_latest_indicators(symbol)
    if ind_data and not redis_snapshot_matches_symbol(symbol, ind_data):
        logger.warning(
            "agent_analysis_indicators_symbol_mismatch",
            symbol=symbol,
            stored=ind_data.get("symbol"),
        )
        ind_data = None

    if regime_data and not redis_snapshot_matches_symbol(symbol, regime_data):
        logger.warning(
            "agent_analysis_regime_symbol_mismatch",
            symbol=symbol,
            stored=regime_data.get("symbol"),
        )
        regime_data = None

    if not ind_data or not regime_data:
        recomputed_ind, recomputed_reg = await _recompute_market_metrics(symbol)
        if not ind_data:
            ind_data = recomputed_ind
        if not regime_data:
            regime_data = recomputed_reg

    if not price_data or not ind_data or not regime_data:
        logger.warning(
            "agent_analysis_missing_context",
            symbol=symbol,
            has_price=bool(price_data),
            has_indicators=bool(ind_data),
            has_regime=bool(regime_data),
        )
        return None

    return price_data, ind_data, regime_data


async def run_agent_analysis(symbol: str, *, force: bool = False) -> AgentConsensus | None:
    """Build consensus from cached price/indicators/regime and publish to Redis + WS."""
    if not is_market_open(symbol):
        return None

    if not force:
        existing = await get_agent_consensus(symbol)
        if existing:
            try:
                cached = AgentConsensus(**existing)
                if cached.verdicts and cached.is_llm_powered():
                    return cached
            except Exception:
                pass

    async with _agent_analysis_lock:
        global _last_agent_run_finished_at
        await _wait_agent_run_slot()
        try:
            context = await _load_market_context(symbol)
            if not context:
                return None

            price_data, ind_data, regime_data = context
            indicators = IndicatorSnapshotSchema(**{**ind_data, "symbol": symbol})
            regime = RegimeSnapshotSchema(**{**regime_data, "symbol": symbol})
            indicators, regime = bind_indicator_regime_to_symbol(symbol, indicators, regime)

            if await is_feed_poll_stale(symbol):
                logger.warning("agent_analysis_feed_stale_recovering", symbol=symbol)
                await recover_feed(symbol, "pre_agent_recovery")

            result: AgentConsensus | None = None
            trigger_price = 0.0
            trigger_source = "frankfurter"
            async with AsyncSessionLocal() as session:
                try:
                    await kill_switch.load_from_cache()
                    ks_status = await kill_switch.evaluate(session)
                    snapshot = await build_market_snapshot(
                        symbol=symbol,
                        price=float(price_data["price"]),
                        indicators=indicators,
                        regime=regime,
                        kill_switch=ks_status,
                    )
                    consensus = await agent_orchestrator.run(snapshot, session=session)
                    if not consensus.verdicts:
                        logger.warning("agent_analysis_empty_verdicts", symbol=symbol)
                        return None
                    if not consensus.is_llm_powered():
                        logger.warning(
                            "agent_analysis_llm_fallback",
                            symbol=symbol,
                            error=consensus.verdicts[0].error,
                        )
                        return consensus
                    from app.engines.final_decision_engine import apply_final_decision_to_consensus
                    from app.services.pipeline import compute_snr_for_symbol, get_symbol_ohlcv_bars

                    snr_snapshot = await compute_snr_for_symbol(symbol)
                    bars = await get_symbol_ohlcv_bars(symbol)
                    consensus = apply_final_decision_to_consensus(
                        consensus,
                        bars=bars,
                        snr=snr_snapshot,
                    )
                    consensus = consensus.model_copy(
                        update={
                            "signal_decision": consensus.signal_decision or "none",
                            "rejection_reason_ar": (
                                rejection_reason_ar(consensus.rejection_reason)
                                if consensus.rejection_reason
                                else consensus.rejection_reason_ar
                            ),
                        }
                    )
                    data = consensus.model_dump(mode="json")
                    await set_agent_consensus(symbol, data)
                    await broadcaster.broadcast_agent_consensus(data)
                    await session.commit()
                    logger.info(
                        "agent_analysis_complete",
                        symbol=symbol,
                        direction=consensus.final_direction.value,
                        verdicts=len(consensus.verdicts),
                    )
                    trigger_price = float(price_data["price"])
                    trigger_source = price_data.get("source") or "frankfurter"
                    result = consensus
                except Exception as exc:
                    await session.rollback()
                    logger.error("agent_analysis_failed", symbol=symbol, error=str(exc))
                    return None

            from app.config.assets import get_asset
            from app.feeds.fx_rate_client import build_hourly_bar

            asset = get_asset(symbol)
            if asset and asset.feed_type == "frankfurter" and result is not None:
                signal_bar = build_hourly_bar(
                    apex_symbol=symbol,
                    price=trigger_price,
                    source=trigger_source,
                    is_closed=True,
                )
                await process_bar(signal_bar, skip_agents=True)
            return result
        finally:
            _last_agent_run_finished_at = time.monotonic()


async def ensure_agent_consensus_for_active_symbols(*, force: bool = False) -> None:
    from app.config.assets import ACTIVE_SYMBOLS

    symbols = [sym for sym in ACTIVE_SYMBOLS if is_market_open(sym)]
    if not symbols:
        return

    for sym in symbols:
        if force:
            await run_agent_analysis(sym, force=True)
            continue
        existing = await get_agent_consensus(sym)
        if existing:
            try:
                cached = AgentConsensus(**existing)
                if cached.verdicts and cached.is_llm_powered():
                    continue
            except Exception:
                pass
        await run_agent_analysis(sym)
