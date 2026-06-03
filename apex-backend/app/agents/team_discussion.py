"""Three-round team discussion agent service."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.agents.combined_agent import CombinedAgentService
from app.agents.market_analyst.agent import AGENT_NAME_AR as MA_NAME, WEIGHT as MA_WEIGHT
from app.agents.news.agent import AGENT_NAME_AR as NEWS_NAME, WEIGHT as NEWS_WEIGHT
from app.agents.risk.agent import AGENT_NAME_AR as RISK_NAME, WEIGHT as RISK_WEIGHT
from app.agents.team_prompt import SYSTEM_PROMPT, build_team_user_prompt
from app.schemas.agent import (
    AgentRole,
    AgentVerdict,
    MarketSnapshot,
    TeamDiscussionLLMOutput,
    TeamRoundOpinion,
)
from app.utils.llm_client import LLMClient, LLMClientError, llm_client


class TeamDiscussionService:
    ROLE_MAP = {
        "market_analyst": (AgentRole.MARKET_ANALYST, MA_NAME, MA_WEIGHT),
        "risk": (AgentRole.RISK, RISK_NAME, RISK_WEIGHT),
        "news": (AgentRole.NEWS, NEWS_NAME, NEWS_WEIGHT),
    }

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or llm_client
        self._fallback = CombinedAgentService(client=self.client)

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> tuple[list[AgentVerdict], bool, str | None, TeamDiscussionLLMOutput | None, str | None]:
        """Return (verdicts, used_llm, error, team_discussion, llm_provider)."""
        start = time.monotonic()

        if not self.client.is_configured:
            verdicts = self._fallback._rule_based_verdicts(snapshot, start)
            return verdicts, False, None, None, None

        try:
            output, response = await self.client.structured_completion(
                SYSTEM_PROMPT,
                build_team_user_prompt(snapshot),
                TeamDiscussionLLMOutput,
                symbol=snapshot.symbol,
            )
            latency = response.latency_ms
            now = datetime.now(timezone.utc)
            verdicts = self._build_verdicts_from_round1(output.round1_initial, latency, now)
            return verdicts, True, None, output, response.provider
        except LLMClientError as exc:
            verdicts = self._fallback._rule_based_verdicts(snapshot, start)
            return verdicts, False, str(exc), None, None

    def _build_verdicts_from_round1(
        self,
        round1: dict[str, TeamRoundOpinion],
        latency: float,
        analyzed_at: datetime,
    ) -> list[AgentVerdict]:
        verdicts: list[AgentVerdict] = []
        for key, (role, name_ar, weight) in self.ROLE_MAP.items():
            opinion = round1.get(key)
            if not opinion:
                continue
            verdicts.append(
                AgentVerdict(
                    agent_id=role,
                    agent_name_ar=name_ar,
                    direction=opinion.direction,
                    confidence=opinion.confidence,
                    reasoning=opinion.reasoning,
                    weight=weight,
                    latency_ms=round(latency / 3, 2),
                    used_llm=True,
                    analyzed_at=analyzed_at,
                    is_stale=False,
                )
            )
        return verdicts


team_discussion_service = TeamDiscussionService()
