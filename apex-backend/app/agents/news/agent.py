"""News Agent — macro & event risk assessment."""

import time

from app.agents.news.prompt import SYSTEM_PROMPT, build_user_prompt
from app.config import settings
from app.schemas.agent import AgentLLMOutput, AgentRole, AgentVerdict, MarketSnapshot
from app.schemas import SignalDirection
from app.services.finnhub_calendar import find_imminent_event, minutes_until_event
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

    if snapshot.news_headlines:
        reasoning.append(f"Finnhub: {len(snapshot.news_headlines)} عنوان خبر مرتبط بالأصل")
        reasoning.append(f"أحدث عنوان: {snapshot.news_headlines[0].headline[:120]}")
    else:
        reasoning.append("لا توجد عناوين Finnhub — الاعتماد على السياق العام فقط")

    if snapshot.upcoming_events:
        reasoning.append(
            f"التقويم: {len(snapshot.upcoming_events)} حدث high impact خلال 24 ساعة"
        )
        imminent = find_imminent_event(
            snapshot.upcoming_events,
            snapshot.timestamp,
            within_minutes=settings.economic_calendar_news_warn_minutes,
        )
        if imminent:
            mins = minutes_until_event(imminent.event_time, snapshot.timestamp)
            reasoning.append(
                f"⚠️ تحذير: {imminent.event} ({imminent.country}) خلال {mins:.0f} دقيقة — حذر"
            )
            return AgentLLMOutput(
                direction=SignalDirection.NEUTRAL,
                confidence=0.72,
                reasoning=reasoning,
            )

    reasoning.append(f"السوق في حالة {regime}")

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
