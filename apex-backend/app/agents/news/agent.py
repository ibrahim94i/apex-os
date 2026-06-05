"""News Agent — macro & event risk assessment."""

import time

from app.agents.news.prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    flatten_news_reasoning,
)
from app.config import settings
from app.schemas.agent import AgentRole, AgentVerdict, MarketSnapshot, NewsAgentLLMOutput
from app.schemas import SignalDirection
from app.services.finnhub_calendar import find_imminent_event, minutes_until_event
from app.utils.llm_client import LLMClient, LLMClientError, llm_client


AGENT_NAME_AR = "وكيل الأخبار"
WEIGHT = 0.25

_ASSETS = ("BTCUSDT", "XAUUSD", "EURUSD", "USDJPY", "GBPUSD")


def _headline_sentiment(item) -> str:
    if item.sentiment_label:
        return item.sentiment_label
    if item.sentiment_score is not None:
        if item.sentiment_score > 0.15:
            return "إيجابي"
        if item.sentiment_score < -0.15:
            return "سلبي"
    return "محايد"


def _assess_news_risk(snapshot: MarketSnapshot) -> tuple[str, float]:
    """Heuristic risk score from headline sentiments."""
    if not snapshot.news_headlines:
        return "medium", 0.55

    scores = [
        h.sentiment_score
        for h in snapshot.news_headlines[:10]
        if h.sentiment_score is not None
    ]
    if not scores:
        return "medium", 0.55

    avg = sum(scores) / len(scores)
    bearish = sum(1 for s in scores if s < -0.15)
    bullish = sum(1 for s in scores if s > 0.15)

    if bearish >= 3 and avg < -0.1:
        return "high", 0.72
    if bullish >= 3 and avg > 0.1:
        return "low", 0.62
    return "medium", 0.58


def _rule_based(snapshot: MarketSnapshot) -> NewsAgentLLMOutput:
    reasoning: list[str] = []

    if snapshot.feed_stale:
        reasoning.append("بيانات السوق قديمة — حذر من الأحداث غير المنعكسة")
        return NewsAgentLLMOutput(
            direction=SignalDirection.NEUTRAL,
            confidence=0.7,
            reasoning=reasoning,
            overall_risk_level="high",
            recommendation_ar="انتظار — بيانات قديمة",
        )

    regime = snapshot.regime.regime.value
    risk_level, base_conf = _assess_news_risk(snapshot)

    if snapshot.news_headlines:
        providers = {h.provider or h.source for h in snapshot.news_headlines[:10]}
        reasoning.append(
            f"مصادر متعددة ({len(providers)}): {', '.join(sorted(p for p in providers if p))}"
        )
        for item in snapshot.news_headlines[:3]:
            reasoning.append(
                f"[{item.provider or item.source}] {item.headline[:80]} — {_headline_sentiment(item)}"
            )
    else:
        reasoning.append("لا توجد عناوين — الاعتماد على السياق العام فقط")

    asset_impacts = {asset: "neutral" for asset in _ASSETS}
    if snapshot.symbol in asset_impacts:
        if risk_level == "high":
            asset_impacts[snapshot.symbol] = "negative"
        elif risk_level == "low":
            asset_impacts[snapshot.symbol] = "positive"

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
            return NewsAgentLLMOutput(
                direction=SignalDirection.NEUTRAL,
                confidence=0.72,
                reasoning=reasoning,
                asset_impacts=asset_impacts,
                overall_risk_level="critical",
                recommendation_ar="انتظار — حدث اقتصادي وشيك",
            )

    if regime == "VOLATILE":
        reasoning.append("تذبذب عالي — احتمال أخبار macro مؤثرة")
        risk_level = "high"

    reasoning.append(f"السوق في حالة {regime}")

    if regime == "TRENDING_UP" and risk_level != "high":
        direction = SignalDirection.LONG
    elif regime == "TRENDING_DOWN" and risk_level != "high":
        direction = SignalDirection.SHORT
    else:
        direction = SignalDirection.NEUTRAL

    rec_map = {
        SignalDirection.LONG: "شراء — الأخبار تدعم الاتجاه",
        SignalDirection.SHORT: "بيع — الأخبار تدعم الهبوط",
        SignalDirection.NEUTRAL: "انتظار — لا توصية واضحة من الأخبار",
    }

    return NewsAgentLLMOutput(
        direction=direction,
        confidence=base_conf,
        reasoning=reasoning,
        asset_impacts=asset_impacts,
        overall_risk_level=risk_level,  # type: ignore[arg-type]
        recommendation_ar=rec_map[direction],
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
                    NewsAgentLLMOutput,
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
            reasoning=flatten_news_reasoning(output),
            weight=WEIGHT,
            latency_ms=round(latency_ms, 2),
            used_llm=used_llm,
            error=error,
        )
