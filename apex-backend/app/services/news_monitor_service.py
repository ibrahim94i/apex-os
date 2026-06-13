"""Five-minute news monitoring — news agent LLM + high-impact calendar checks."""

from __future__ import annotations

import asyncio
import time

from app.agents.news.agent import NewsAgent
from app.agents.voting.weighted_engine import AdaptiveWeightedEngine
from app.config import settings
from app.core.cache import (
    get_agent_consensus,
    set_agent_consensus,
    set_news_verdict,
)
from app.database import AsyncSessionLocal
from app.engines.kill_switch import kill_switch
from app.logging_config import logger
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict, MarketSnapshot
from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema
from app.services.economic_calendar_gate import check_economic_calendar_gate
from app.services.finnhub_calendar import (
    _load_high_impact_events,
    find_imminent_event,
)
from app.services.market_hours import is_market_open
from app.services.market_snapshot import bind_indicator_regime_to_symbol, build_market_snapshot
from app.services.signal_filters import detect_high_impact_news, set_news_block
from app.services.agent_analysis_service import _load_market_context, _serve_stale_if_llm_blocked
from app.websocket.manager import broadcaster

_news_monitor_lock = asyncio.Lock()
_last_news_run_finished_at: float = 0.0
_voting_engine = AdaptiveWeightedEngine()
_news_agent = NewsAgent()


async def _wait_news_slot() -> None:
    global _last_news_run_finished_at
    gap = settings.llm_min_request_interval_seconds
    wait = gap - (time.monotonic() - _last_news_run_finished_at)
    if wait > 0:
        await asyncio.sleep(wait)


async def monitor_high_impact_calendar(symbol: str, at) -> None:
    """Set news block when a high-impact event is imminent or in blackout."""
    events = await _load_high_impact_events()
    safe, reason = check_economic_calendar_gate(events, at)
    if not safe:
        await set_news_block(symbol)
        logger.warning(
            "high_impact_calendar_block",
            symbol=symbol,
            reason=reason,
        )
        return

    imminent = find_imminent_event(
        events,
        at,
        within_minutes=settings.economic_calendar_news_warn_minutes,
    )
    if imminent:
        await set_news_block(symbol)
        logger.warning(
            "high_impact_calendar_imminent",
            symbol=symbol,
            event=imminent.event,
            country=imminent.country,
        )


async def _refresh_consensus_with_news(
    symbol: str,
    news_verdict: AgentVerdict,
    snapshot: MarketSnapshot,
) -> None:
    """Re-vote using cached H1 market/risk verdicts + fresh news — no signals."""
    cached_raw = await get_agent_consensus(symbol)
    h1_verdicts: list[AgentVerdict] = []
    team_discussion = None
    llm_provider = None

    if cached_raw:
        try:
            cached = AgentConsensus(**cached_raw)
            h1_verdicts = [
                v
                for v in cached.verdicts
                if v.agent_id in (AgentRole.MARKET_ANALYST, AgentRole.RISK)
            ]
            team_discussion = cached.team_discussion
            llm_provider = cached.llm_provider
        except Exception:
            pass

    if not h1_verdicts:
        data = news_verdict.model_dump(mode="json")
        await set_news_verdict(symbol, data)
        partial = AgentConsensus(
            symbol=symbol,
            timestamp=snapshot.timestamp,
            final_direction=news_verdict.direction,
            final_confidence=news_verdict.confidence,
            verdicts=[news_verdict],
            vote_scores={},
            reasoning_summary=news_verdict.reasoning[:3],
            llm_provider="openai" if news_verdict.used_llm else None,
        )
        consensus_data = partial.model_dump(mode="json")
        await set_agent_consensus(symbol, consensus_data)
        await broadcaster.broadcast_agent_consensus(consensus_data)
        return

    verdicts = h1_verdicts + [news_verdict]
    regime = snapshot.regime.regime.value
    async with AsyncSessionLocal() as session:
        consensus = await _voting_engine.vote(
            symbol, verdicts, regime=regime, session=session, snapshot=snapshot
        )

    if team_discussion:
        consensus = consensus.model_copy(
            update={
                "team_discussion": team_discussion,
                "discussion_summary_ar": team_discussion.discussion_summary,
                "llm_provider": llm_provider,
            }
        )

    if detect_high_impact_news(consensus):
        await set_news_block(symbol)

    if cached_raw:
        try:
            prev = AgentConsensus(**cached_raw)
            consensus = consensus.model_copy(
                update={
                    "signal_decision": prev.signal_decision,
                    "rejection_reason": prev.rejection_reason,
                    "rejection_reason_ar": prev.rejection_reason_ar,
                    "proposed_direction": prev.proposed_direction,
                    "proposed_confidence": prev.proposed_confidence,
                    "snr_warning_ar": prev.snr_warning_ar,
                    "final_decision": prev.final_decision,
                    "final_decision_ar": prev.final_decision_ar,
                    "is_stale": False,
                    "stale_warning_ar": None,
                }
            )
        except Exception:
            pass

    data = consensus.model_dump(mode="json")
    await set_agent_consensus(symbol, data)
    await broadcaster.broadcast_agent_consensus(data)


async def run_news_monitor_for_symbol(symbol: str) -> None:
    if not is_market_open(symbol) and not settings.agents_run_when_market_closed:
        return

    blocked = await _serve_stale_if_llm_blocked(symbol)
    if blocked:
        return

    context = await _load_market_context(symbol)
    if not context:
        logger.warning("news_monitor_missing_context", symbol=symbol)
        return

    price_data, ind_data, regime_data = context
    indicators = IndicatorSnapshotSchema(**{**ind_data, "symbol": symbol})
    regime = RegimeSnapshotSchema(**{**regime_data, "symbol": symbol})
    indicators, regime = bind_indicator_regime_to_symbol(symbol, indicators, regime)

    async with AsyncSessionLocal() as session:
        await kill_switch.load_from_cache()
        ks_status = await kill_switch.evaluate(session)
        snapshot = await build_market_snapshot(
            symbol=symbol,
            price=float(price_data["price"]),
            indicators=indicators,
            regime=regime,
            kill_switch=ks_status,
        )

    await monitor_high_impact_calendar(symbol, snapshot.timestamp)

    async with _news_monitor_lock:
        global _last_news_run_finished_at
        await _wait_news_slot()
        try:
            news_verdict = await _news_agent.analyze(snapshot)
            await set_news_verdict(symbol, news_verdict.model_dump(mode="json"))
            await _refresh_consensus_with_news(symbol, news_verdict, snapshot)
            logger.info(
                "news_monitor_complete",
                symbol=symbol,
                direction=news_verdict.direction.value,
                used_llm=news_verdict.used_llm,
            )
        finally:
            _last_news_run_finished_at = time.monotonic()


async def run_news_monitor_cycle() -> None:
    from app.config.assets import ACTIVE_SYMBOLS

    if settings.agents_run_when_market_closed:
        symbols = list(ACTIVE_SYMBOLS)
    else:
        symbols = [sym for sym in ACTIVE_SYMBOLS if is_market_open(sym)]
    for index, sym in enumerate(symbols):
        if index > 0:
            await asyncio.sleep(settings.llm_min_request_interval_seconds)
        await run_news_monitor_for_symbol(sym)
