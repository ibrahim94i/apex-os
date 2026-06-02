"""News Agent — macro & event risk assessment."""

import time

from app.agents.news.prompt import SYSTEM_PROMPT, build_user_prompt
from app.schemas.agent import AgentLLMOutput, AgentRole, AgentVerdict, MarketSnapshot
from app.schemas import SignalDirection
from app.utils.llm_client import LLMClient, LLMClientError, llm_client


AGENT_NAME_AR = "وكيل الأخبار"
WEIGHT = 0.25


def _rule_based(snapshot: MarketSnapshot) -> AgentLLMOutput:
    reasoning: list[str] = []

    if snapshot.feed_stale:
        reasoning.append("بيانات السوق قديمة — حذر من الأحداث غير المنعكسة")
        return AgentLLMOutput(
            direction=SignalDirection.NEUTRAL,
            confidence=0.7,
            reasoning=reasoning,
        )

    regime = snapshot.regime.regime.value
    if regime == "VOLATILE":
        reasoning.append("تذبذب عالي — احتمال أخبار أو أحداث macro مؤثرة")
        reasoning.append("يُفضل انتظار استقرار السوق قبل الدخول")
        return AgentLLMOutput(
            direction=SignalDirection.NEUTRAL,
            confidence=0.65,
            reasoning=reasoning,
        )

    reasoning.append("لا توجد أحداث إخبارية حرجة مكتشفة في النافذة الزمنية")
    reasoning.append(f"السوق في حالة {regime} — بيئة إخبارية مستقرة نسبياً")

    if regime == "TRENDING_UP":
        direction = SignalDirection.LONG
    elif regime == "TRENDING_DOWN":
        direction = SignalDirection.SHORT
    else:
        direction = SignalDirection.NEUTRAL

    return AgentLLMOutput(
        direction=direction,
        confidence=0.55,
        reasoning=reasoning,
    )


class NewsAgent:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or llm_client

    async def analyze(self, snapshot: MarketSnapshot) -> AgentVerdict:
        start = time.monotonic()
        used_llm = False
        error: str | None = None

        try:
            if self.client.is_configured:
                output, response = await self.client.structured_completion(
                    SYSTEM_PROMPT,
                    build_user_prompt(snapshot),
                    AgentLLMOutput,
                    symbol=snapshot.symbol,
                )
                used_llm = True
                latency_ms = response.latency_ms
            else:
                output = _rule_based(snapshot)
                latency_ms = (time.monotonic() - start) * 1000
        except LLMClientError as exc:
            error = str(exc)
            output = _rule_based(snapshot)
            latency_ms = (time.monotonic() - start) * 1000

        return AgentVerdict(
            agent_id=AgentRole.NEWS,
            agent_name_ar=AGENT_NAME_AR,
            direction=output.direction,
            confidence=output.confidence,
            reasoning=output.reasoning,
            weight=WEIGHT,
            latency_ms=round(latency_ms, 2),
            used_llm=used_llm,
            error=error,
        )
