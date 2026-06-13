"""Agent orchestrator — H1 team discussion + cached news verdict + weighted voting."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.team_discussion import team_discussion_service
from app.agents.voting.weighted_engine import AdaptiveWeightedEngine
from app.config import settings
from app.core.cache import get_agent_consensus, get_news_verdict, set_news_verdict
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

    async def _load_news_verdict(self, symbol: str) -> AgentVerdict | None:
        raw = await get_news_verdict(symbol)
        if raw:
            try:
                verdict = AgentVerdict(**raw)
                if verdict.agent_id == AgentRole.NEWS:
                    return verdict
            except Exception:
                pass

        cached = await get_agent_consensus(symbol)
        if cached:
            try:
                consensus = AgentConsensus(**cached)
                for verdict in consensus.verdicts:
                    if verdict.agent_id == AgentRole.NEWS:
                        return verdict
            except Exception:
                pass
        return None

    async def _ensure_news_verdict(
        self, symbol: str, snapshot: MarketSnapshot | None = None
    ) -> AgentVerdict | None:
        """Load cached news verdict or run the news agent when missing."""
        news = await self._load_news_verdict(symbol)
        if news is not None:
            return news
        if snapshot is None:
            return None

        from app.agents.news.agent import NewsAgent

        try:
            news = await NewsAgent().analyze(snapshot)
            await set_news_verdict(symbol, news.model_dump(mode="json"))
            return news
        except Exception:
            return None

    async def _merge_verdicts(
        self,
        symbol: str,
        h1_verdicts: list[AgentVerdict],
        snapshot: MarketSnapshot | None = None,
    ) -> list[AgentVerdict]:
        news = await self._ensure_news_verdict(symbol, snapshot)
        if news is None:
            return h1_verdicts
        merged = [v for v in h1_verdicts if v.agent_id != AgentRole.NEWS]
        merged.append(news)
        return merged

    async def run_h1(
        self, snapshot: MarketSnapshot, session: AsyncSession | None = None
    ) -> AgentConsensus:
        """Run market analyst + risk at H1 close; merge cached news verdict for voting."""
        cached = await get_cached_consensus(snapshot)
        if cached:
            news = await self._ensure_news_verdict(snapshot.symbol, snapshot)
            if news is not None:
                h1_verdicts = [v for v in cached.verdicts if v.agent_id != AgentRole.NEWS]
                if len(h1_verdicts) >= 2:
                    merged = await self._merge_verdicts(snapshot.symbol, h1_verdicts, snapshot)
                    return await self._vote_from_verdicts(
                        snapshot, merged, cached.team_discussion, cached.llm_provider, session
                    )
            return cached.model_copy(update={"symbol": snapshot.symbol})

        verdicts, used_llm, error, team_discussion, llm_provider = await self.team_service.analyze_h1(
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

        all_verdicts = await self._merge_verdicts(snapshot.symbol, verdicts, snapshot)
        consensus = await self._vote_from_verdicts(
            snapshot, all_verdicts, team_discussion, llm_provider, session
        )

        if used_llm:
            await set_cached_consensus(
                snapshot,
                consensus,
                ttl_seconds=settings.h1_agent_cache_ttl_seconds,
            )

        return consensus

    async def run(
        self, snapshot: MarketSnapshot, session: AsyncSession | None = None
    ) -> AgentConsensus:
        """Backward-compatible alias — H1 path only."""
        return await self.run_h1(snapshot, session=session)

    async def _vote_from_verdicts(
        self,
        snapshot: MarketSnapshot,
        verdicts: list[AgentVerdict],
        team_discussion,
        llm_provider: str | None,
        session: AsyncSession | None,
    ) -> AgentConsensus:
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

        return consensus


agent_orchestrator = AgentOrchestrator()
