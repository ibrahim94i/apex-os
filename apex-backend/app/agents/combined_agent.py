"""Single combined Groq call for all three agents."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.agents.combined_prompt import SYSTEM_PROMPT, build_combined_user_prompt
from app.agents.market_analyst.agent import AGENT_NAME_AR as MA_NAME, WEIGHT as MA_WEIGHT, _rule_based as ma_rule
from app.agents.news.agent import AGENT_NAME_AR as NEWS_NAME, WEIGHT as NEWS_WEIGHT, _rule_based as news_rule
from app.agents.risk.agent import AGENT_NAME_AR as RISK_NAME, WEIGHT as RISK_WEIGHT, _rule_based as risk_rule
from app.agents.news.prompt import flatten_news_reasoning
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict, CombinedAgentLLMOutput, MarketSnapshot
from app.utils.llm_client import LLMClient, LLMClientError, llm_client


class CombinedAgentService:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or llm_client

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> tuple[list[AgentVerdict], bool, str | None]:
        """Return (verdicts, used_llm, error)."""
        start = time.monotonic()

        if not self.client.is_configured:
            return self._rule_based_verdicts(snapshot, start), False, None

        try:
            output, response = await self.client.structured_completion(
                SYSTEM_PROMPT,
                build_combined_user_prompt(snapshot),
                CombinedAgentLLMOutput,
                symbol=snapshot.symbol,
            )
            latency = response.latency_ms
            verdicts = [
                AgentVerdict(
                    agent_id=AgentRole.MARKET_ANALYST,
                    agent_name_ar=MA_NAME,
                    direction=output.market_analyst.direction,
                    confidence=output.market_analyst.confidence,
                    reasoning=output.market_analyst.reasoning,
                    weight=MA_WEIGHT,
                    latency_ms=round(latency / 3, 2),
                    used_llm=True,
                ),
                AgentVerdict(
                    agent_id=AgentRole.RISK,
                    agent_name_ar=RISK_NAME,
                    direction=output.risk.direction,
                    confidence=output.risk.confidence,
                    reasoning=output.risk.reasoning,
                    weight=RISK_WEIGHT,
                    latency_ms=round(latency / 3, 2),
                    used_llm=True,
                ),
                AgentVerdict(
                    agent_id=AgentRole.NEWS,
                    agent_name_ar=NEWS_NAME,
                    direction=output.news.direction,
                    confidence=output.news.confidence,
                    reasoning=flatten_news_reasoning(output.news),
                    weight=NEWS_WEIGHT,
                    latency_ms=round(latency / 3, 2),
                    used_llm=True,
                ),
            ]
            return verdicts, True, None
        except LLMClientError as exc:
            return self._rule_based_verdicts(snapshot, start), False, str(exc)

    def _rule_based_verdicts(
        self,
        snapshot: MarketSnapshot,
        start: float,
        *,
        fallback_error: str | None = None,
    ) -> list[AgentVerdict]:
        latency = (time.monotonic() - start) * 1000
        ma = ma_rule(snapshot)
        risk = risk_rule(snapshot)
        news = news_rule(snapshot)
        err = fallback_error
        return [
            AgentVerdict(
                agent_id=AgentRole.MARKET_ANALYST,
                agent_name_ar=MA_NAME,
                direction=ma.direction,
                confidence=ma.confidence,
                reasoning=ma.reasoning,
                weight=MA_WEIGHT,
                latency_ms=round(latency / 3, 2),
                used_llm=False,
                error=err,
            ),
            AgentVerdict(
                agent_id=AgentRole.RISK,
                agent_name_ar=RISK_NAME,
                direction=risk.direction,
                confidence=risk.confidence,
                reasoning=risk.reasoning,
                weight=RISK_WEIGHT,
                latency_ms=round(latency / 3, 2),
                used_llm=False,
                error=err,
            ),
            AgentVerdict(
                agent_id=AgentRole.NEWS,
                agent_name_ar=NEWS_NAME,
                direction=news.direction,
                confidence=news.confidence,
                reasoning=flatten_news_reasoning(news),
                weight=NEWS_WEIGHT,
                latency_ms=round(latency / 3, 2),
                used_llm=False,
                error=err,
            ),
        ]


combined_agent_service = CombinedAgentService()
