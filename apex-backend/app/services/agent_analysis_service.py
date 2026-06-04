"""Run agent consensus from cached market data when the pipeline has not yet."""

from __future__ import annotations

from app.agents.orchestrator import agent_orchestrator
from app.core.cache import (
    get_agent_consensus,
    get_latest_indicators,
    get_latest_price,
    get_latest_regime,
    set_agent_consensus,
)
from app.database import AsyncSessionLocal
from app.engines.kill_switch import kill_switch
from app.logging_config import logger
from app.schemas import (
    AgentConsensus,
    IndicatorSnapshotSchema,
    RegimeSnapshotSchema,
)
from app.services.market_hours import is_market_open
from app.services.market_snapshot import build_market_snapshot
from app.services.signal_rejection_i18n import rejection_reason_ar
from app.websocket.manager import broadcaster


async def run_agent_analysis(symbol: str, *, force: bool = False) -> AgentConsensus | None:
    """Build consensus from cached price/indicators/regime and publish to Redis + WS."""
    if not is_market_open(symbol):
        return None

    if not force:
        existing = await get_agent_consensus(symbol)
        if existing:
            try:
                return AgentConsensus(**existing)
            except Exception:
                pass

    price_data = await get_latest_price(symbol)
    ind_data = await get_latest_indicators(symbol)
    regime_data = await get_latest_regime(symbol)
    if not price_data or not ind_data or not regime_data:
        logger.debug("agent_analysis_skipped_missing_data", symbol=symbol)
        return None

    indicators = IndicatorSnapshotSchema(**ind_data)
    regime = RegimeSnapshotSchema(**regime_data)

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
            return consensus
        except Exception as exc:
            await session.rollback()
            logger.error("agent_analysis_failed", symbol=symbol, error=str(exc))
            return None


async def ensure_agent_consensus_for_active_symbols(*, force: bool = False) -> None:
    from app.config.assets import ACTIVE_SYMBOLS

    for symbol in ACTIVE_SYMBOLS:
        if not is_market_open(symbol):
            continue
        if not force and await get_agent_consensus(symbol):
            continue
        await run_agent_analysis(symbol, force=force)
