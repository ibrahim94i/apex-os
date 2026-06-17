"""SNR compute + consensus enrichment helpers."""

from __future__ import annotations

from app.logging_config import logger
from app.schemas.agent import AgentConsensus
from app.services.pipeline import compute_snr_for_symbol, fetch_decision_bars


async def enrich_consensus_with_snr(
    consensus: AgentConsensus,
    symbol: str,
    *,
    persist: bool = False,
) -> AgentConsensus:
    """Attach fresh SNR state/levels to consensus for dashboard display."""
    from app.core.cache import set_agent_consensus
    from app.engines.final_decision_engine import apply_final_decision_to_consensus
    from app.services.signal_rejection_i18n import normalize_snr_consensus_fields
    from app.websocket.manager import broadcaster

    snr_snapshot = await compute_snr_for_symbol(symbol, use_live_price=True)
    bars = await fetch_decision_bars(symbol)
    current_price: float | None = None
    if bars:
        current_price = bars[-1].close
    if not bars and snr_snapshot is None:
        logger.warning("snr_enrichment_skipped", symbol=symbol, reason="no_bars")
        return consensus

    enriched = apply_final_decision_to_consensus(
        consensus,
        bars=bars,
        snr=snr_snapshot,
        current_price=current_price,
    )
    rr, rr_ar, warning = normalize_snr_consensus_fields(
        rejection_reason=enriched.rejection_reason,
        rejection_reason_ar=enriched.rejection_reason_ar,
        snr_warning_ar=enriched.snr_warning_ar,
        final_decision=enriched.final_decision,
    )
    enriched = enriched.model_copy(
        update={
            "rejection_reason": rr,
            "rejection_reason_ar": rr_ar,
            "snr_warning_ar": warning,
        }
    )

    if snr_snapshot:
        from app.core.cache import set_latest_snr

        await set_latest_snr(symbol, snr_snapshot.model_dump(mode="json"))
    else:
        logger.warning(
            "snr_snapshot_empty",
            symbol=symbol,
            bars=len(bars),
        )

    if persist:
        data = enriched.model_dump(mode="json")
        await set_agent_consensus(symbol, data)
        await broadcaster.broadcast_agent_consensus(data)

    return enriched
