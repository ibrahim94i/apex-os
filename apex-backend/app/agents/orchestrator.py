"""Agent orchestrator — single combined LLM call + cache."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.combined_agent import combined_agent_service
from app.agents.voting.weighted_engine import AdaptiveWeightedEngine
from app.schemas import SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict, MarketSnapshot
from app.services.agent_cache import get_cached_consensus, set_cached_consensus


class AgentOrchestrator:
    def __init__(self) -> None:
        self.combined_agent = combined_agent_service
        self.voting_engine = AdaptiveWeightedEngine()

    async def run(
        self, snapshot: MarketSnapshot, session: AsyncSession | None = None
    ) -> AgentConsensus:
        cached = await get_cached_consensus(snapshot)
        if cached:
            return cached

        verdicts, used_llm, error = await self.combined_agent.analyze(snapshot)

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

        regime = snapshot.regime.regime.value
        consensus = await self.voting_engine.vote(
            snapshot.symbol, verdicts, regime=regime, session=session
        )

        if used_llm:
            await set_cached_consensus(snapshot, consensus)

        return consensus


agent_orchestrator = AgentOrchestrator()
