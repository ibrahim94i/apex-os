"""Agent orchestrator — team discussion + freshness + weighted voting."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.team_discussion import team_discussion_service
from app.agents.voting.weighted_engine import AdaptiveWeightedEngine
from app.schemas import SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict, MarketSnapshot
from app.services.agent_cache import get_cached_consensus, set_cached_consensus
from app.services.agent_freshness import (
    annotate_verdict_freshness,
    validate_agent_data_freshness,
)


class AgentOrchestrator:
    def __init__(self) -> None:
        self.team_service = team_discussion_service
        self.voting_engine = AdaptiveWeightedEngine()

    async def run(
        self, snapshot: MarketSnapshot, session: AsyncSession | None = None
    ) -> AgentConsensus:
        cached = await get_cached_consensus(snapshot)
        if cached:
            return cached.model_copy(update={"symbol": snapshot.symbol})

        verdicts, used_llm, error, team_discussion, llm_provider = await self.team_service.analyze(
            snapshot
        )

        if not verdicts:
            return AgentConsensus(
                symbol=snapshot.symbol,
                timestamp=datetime.now(timezone.utc),
                final_direction=SignalDirection.NEUTRAL,
                final_confidence=0.0,
                verdicts=[
                    AgentVerdict(
                        agent_id=AgentRole.MARKET_ANALYST,
                        agent_name_ar="محلل السوق",
                        direction=SignalDirection.NEUTRAL,
                        confidence=0.0,
                        reasoning=["فشل تشغيل الوكلاء"],
                        weight=0.0,
                        error=error or "All agents failed",
                    )
                ],
                vote_scores={},
            )

        # Refresh snapshot clock after LLM — slow API calls must not trigger snapshot_data_too_old
        snapshot = snapshot.model_copy(update={"timestamp": datetime.now(timezone.utc)})
        verdicts = annotate_verdict_freshness(verdicts, snapshot)
        fresh_ok, fresh_reason = validate_agent_data_freshness(snapshot, verdicts)
        if not fresh_ok:
            return AgentConsensus(
                symbol=snapshot.symbol,
                timestamp=datetime.now(timezone.utc),
                final_direction=SignalDirection.NEUTRAL,
                final_confidence=0.0,
                verdicts=verdicts,
                vote_scores={},
                reasoning_summary=[f"رفض القرار: بيانات قديمة ({fresh_reason})"],
                team_discussion=team_discussion,
                llm_provider=llm_provider,
            )

        regime = snapshot.regime.regime.value
        consensus = await self.voting_engine.vote(
            snapshot.symbol, verdicts, regime=regime, session=session, snapshot=snapshot
        )

        if team_discussion:
            consensus = consensus.model_copy(
                update={
                    "team_discussion": team_discussion,
                    "discussion_summary_ar": team_discussion.discussion_summary,
                    # Keep final_direction/final_confidence from weighted voting — do not
                    # overwrite with round3 LLM synthesis (avoids 70% display vs 61.5% math).
                    "reasoning_summary": (
                        consensus.reasoning_summary
                        + team_discussion.discussion_summary
                        + [f"اتفاق: {a}" for a in team_discussion.agreements[:3]]
                        + [f"خلاف: {d}" for d in team_discussion.disagreements[:3]]
                    ),
                    "llm_provider": llm_provider,
                }
            )
        else:
            consensus = consensus.model_copy(update={"llm_provider": llm_provider})

        if used_llm:
            await set_cached_consensus(snapshot, consensus)

        return consensus


agent_orchestrator = AgentOrchestrator()
