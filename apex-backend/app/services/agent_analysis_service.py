"""Run agent consensus from cached market data when the pipeline has not yet."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.agents.orchestrator import agent_orchestrator
from app.config import settings
from app.core.cache import (
    get_agent_consensus,
    get_agent_consensus_last_good,
    get_latest_indicators,
    get_latest_price,
    get_latest_regime,
    set_agent_consensus,
    set_agent_consensus_last_good,
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
from app.services.consensus_utils import consensus_has_h1_agents
from app.services.feed_freshness import is_feed_poll_stale
from app.services.feed_health_service import recover_feed
from app.services.market_data_store import (
    fetch_agent_bars_from_db,
    get_latest_price_from_db,
    get_latest_regime_from_db,
)
from app.services.market_snapshot import (
    bind_indicator_regime_to_symbol,
    build_market_snapshot,
    redis_snapshot_matches_symbol,
)
from app.services.pipeline import process_bar
from app.services.signal_rejection_i18n import rejection_reason_ar
from app.websocket.manager import broadcaster

_signal_generator = SignalGenerator()
_MIN_INDICATOR_BARS = IndicatorEngine().min_bars
_DB_BAR_LIMIT = 500
_agent_analysis_lock = asyncio.Lock()
_batch_consensus_lock = asyncio.Lock()
_last_agent_run_finished_at: float = 0.0
_STALE_WARNING_AR = "بيانات قديمة"


async def _wait_agent_run_slot() -> None:
    """Gap between serialized agent runs to respect LLM rate limits."""
    global _last_agent_run_finished_at
    gap = settings.agent_symbol_gap_seconds
    wait = gap - (time.monotonic() - _last_agent_run_finished_at)
    if wait > 0:
        await asyncio.sleep(wait)


def _consensus_from_cache(raw: dict[str, Any] | None) -> AgentConsensus | None:
    if not raw:
        return None
    try:
        cached = AgentConsensus(**raw)
    except Exception:
        return None
    if not cached.verdicts:
        return None
    return cached


async def _restore_stale_consensus(symbol: str, error: str | None) -> AgentConsensus | None:
    """On LLM failure, re-publish the last good LLM consensus with a stale flag."""
    for getter in (get_agent_consensus_last_good, get_agent_consensus):
        cached = _consensus_from_cache(await getter(symbol))
        if not cached or not cached.is_llm_powered():
            continue
        stale = cached.model_copy(
            update={
                "symbol": symbol,
                "is_stale": True,
                "stale_warning_ar": _STALE_WARNING_AR,
            }
        )
        data = stale.model_dump(mode="json")
        await set_agent_consensus(symbol, data)
        await broadcaster.broadcast_agent_consensus(data)
        logger.warning(
            "agent_analysis_serving_stale_consensus",
            symbol=symbol,
            error=error,
        )
        return stale
    return None


async def _serve_stale_if_llm_blocked(symbol: str) -> AgentConsensus | None:
    from app.utils.llm_circuit_breaker import is_llm_blocked

    if not await is_llm_blocked():
        return None
    cached = _consensus_from_cache(await get_agent_consensus(symbol))
    if cached and (cached.is_llm_powered() or cached.is_stale):
        return cached
    return await _restore_stale_consensus(symbol, "LLM circuit open after 429")


async def _recompute_market_metrics(symbol: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Rebuild indicators/regime from DB OHLCV when Redis cache is empty."""
    bars = await fetch_agent_bars_from_db(symbol, _DB_BAR_LIMIT)
    if len(bars) < _MIN_INDICATOR_BARS:
        logger.warning(
            "agent_analysis_insufficient_bars",
            symbol=symbol,
            bars=len(bars),
            required=_MIN_INDICATOR_BARS,
        )
        return None, None

    from app.services.pipeline import fetch_decision_bars

    decision_bars = await fetch_decision_bars(symbol)
    indicators, regime = _signal_generator.analyze(decision_bars, symbol)
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
    if not is_market_open(symbol) and not settings.agents_run_when_market_closed:
        return None

    if not force:
        cached = _consensus_from_cache(await get_agent_consensus(symbol))
        if (
            cached
            and consensus_has_h1_agents(cached)
            and (cached.is_llm_powered() or cached.is_stale)
        ):
            if not cached.snr_state_ar:
                from app.services.snr_service import enrich_consensus_with_snr

                return await enrich_consensus_with_snr(cached, symbol, persist=True)
            return cached

    blocked = await _serve_stale_if_llm_blocked(symbol)
    if blocked:
        if not blocked.snr_state_ar:
            from app.services.snr_service import enrich_consensus_with_snr

            return await enrich_consensus_with_snr(blocked, symbol, persist=True)
        return blocked

    async with _agent_analysis_lock:
        global _last_agent_run_finished_at
        await _wait_agent_run_slot()
        try:
            blocked = await _serve_stale_if_llm_blocked(symbol)
            if blocked:
                if not blocked.snr_state_ar:
                    from app.services.snr_service import enrich_consensus_with_snr

                    return await enrich_consensus_with_snr(blocked, symbol, persist=True)
                return blocked

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
                    consensus = await agent_orchestrator.run_h1(snapshot, session=session)
                    if not consensus.verdicts:
                        logger.warning("agent_analysis_empty_verdicts", symbol=symbol)
                        return None
                    if not consensus.is_llm_powered():
                        error = consensus.verdicts[0].error if consensus.verdicts else None
                        logger.warning(
                            "agent_analysis_llm_fallback",
                            symbol=symbol,
                            error=error,
                        )
                        stale = await _restore_stale_consensus(symbol, error)
                        if stale:
                            if not stale.snr_state_ar:
                                from app.services.snr_service import enrich_consensus_with_snr

                                return await enrich_consensus_with_snr(stale, symbol, persist=True)
                            return stale
                        from app.services.snr_service import enrich_consensus_with_snr

                        return await enrich_consensus_with_snr(consensus, symbol, persist=True)
                    from app.services.snr_service import enrich_consensus_with_snr

                    consensus = await enrich_consensus_with_snr(consensus, symbol, persist=False)
                    from app.services.signal_rejection_i18n import normalize_snr_consensus_fields

                    rr, rr_ar, warning = normalize_snr_consensus_fields(
                        rejection_reason=consensus.rejection_reason,
                        rejection_reason_ar=consensus.rejection_reason_ar,
                        snr_warning_ar=consensus.snr_warning_ar,
                        final_decision=consensus.final_decision,
                    )
                    consensus = consensus.model_copy(
                        update={
                            "signal_decision": consensus.signal_decision or "none",
                            "rejection_reason": rr,
                            "rejection_reason_ar": rr_ar,
                            "snr_warning_ar": warning,
                            "is_stale": False,
                            "stale_warning_ar": None,
                        }
                    )
                    data = consensus.model_dump(mode="json")
                    await set_agent_consensus(symbol, data)
                    await set_agent_consensus_last_good(symbol, data)
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
    """Run agent analysis sequentially for active symbols with a gap between each."""
    from app.config.assets import ACTIVE_SYMBOLS

    if settings.agents_run_when_market_closed:
        symbols = list(ACTIVE_SYMBOLS)
    else:
        symbols = [sym for sym in ACTIVE_SYMBOLS if is_market_open(sym)]
        if not symbols:
            return

    async with _batch_consensus_lock:
        for index, sym in enumerate(symbols):
            if index > 0:
                await asyncio.sleep(settings.agent_symbol_gap_seconds)
            if force:
                blocked = await _serve_stale_if_llm_blocked(sym)
                if blocked:
                    continue
                await run_agent_analysis(sym, force=True)
                continue
            cached = _consensus_from_cache(await get_agent_consensus(sym))
            if cached and (cached.is_llm_powered() or cached.is_stale):
                continue
            blocked = await _serve_stale_if_llm_blocked(sym)
            if blocked:
                continue
            await run_agent_analysis(sym)
