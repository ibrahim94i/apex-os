"""Prompts for News Agent."""

from app.agents.news.calendar_format import format_economic_calendar_block
from app.agents.prompt_utils import AGENT_JSON_RULES, asset_header
from app.schemas.agent import MarketSnapshot, NewsAgentLLMOutput

NEWS_JSON_SCHEMA = """{
  "direction": "LONG" | "SHORT" | "NEUTRAL",
  "confidence": 0.0-1.0,
  "reasoning": ["سبب 1 بالعربية", "..."],
  "asset_impacts": {
    "XAUUSD": "positive" | "negative" | "neutral",
    "EURUSD": "positive" | "negative" | "neutral",
    "USDJPY": "positive" | "negative" | "neutral",
    "GBPUSD": "positive" | "negative" | "neutral"
  },
  "overall_risk_level": "low" | "medium" | "high" | "critical",
  "recommendation_ar": "توصية واضحة بناءً على الأخبار فقط"
}"""

SYSTEM_PROMPT = f"""أنت وكيل أخبار macro متخصص في تقييم تأثير الأحداث على التداول.
حلل السياق لأي أصل (BTCUSDT, XAUUSD, EURUSD, USDJPY, GBPUSD) وأعد JSON فقط:
{NEWS_JSON_SCHEMA}
{AGENT_JSON_RULES}
- المصادر: Finnhub, Alpha Vantage, Reuters, Bloomberg, CNBC, MarketWatch, Investing.com, FXStreet
- لكل خبر في reasoning: اذكر المصدر، sentiment (إيجابي/سلبي/محايد)، وتأثيره المختصر
- asset_impacts: تأثير الأخبار المجمّعة على كل أصل (positive=إيجابي, negative=سلبي, neutral=محايد)
- overall_risk_level: مستوى الخطر الإجمالي من الأخبار والتقويم
- recommendation_ar: توصية تداول واضحة بناءً على الأخبار فقط (شراء/بيع/انتظار)
- إن وُجد حدث high impact خلال 60 دقيقة: overall_risk_level=critical ويُفضّل NEUTRAL
- إذا كانت البيانات قديمة أو التذبذب عالياً، كن حذراً"""


def _sentiment_display(item) -> str:
    if item.sentiment_label:
        return item.sentiment_label
    if item.sentiment_score is not None:
        if item.sentiment_score > 0.15:
            return "إيجابي"
        if item.sentiment_score < -0.15:
            return "سلبي"
        return "محايد"
    return "غير محدد"


def format_news_block(snapshot: MarketSnapshot) -> str:
    if not snapshot.news_headlines:
        return "آخر الأخبار الاقتصادية (جميع المصادر): غير متوفرة — اعتمد على السياق العام فقط"
    lines = ["آخر الأخبار الاقتصادية (Finnhub + Alpha Vantage + RSS):"]
    for idx, item in enumerate(snapshot.news_headlines[:15], start=1):
        when = (
            item.published_at.strftime("%Y-%m-%d %H:%M UTC")
            if item.published_at
            else "—"
        )
        provider = item.provider or item.source or "unknown"
        sentiment = _sentiment_display(item)
        lines.append(
            f"{idx}. [{provider}/{item.source or provider}] {item.headline} ({when}) — sentiment: {sentiment}"
        )
        if item.summary:
            lines.append(f"   ملخص: {item.summary[:280]}")
    return "\n".join(lines)


def format_finnhub_news_block(snapshot: MarketSnapshot) -> str:
    """Backward-compatible alias."""
    return format_news_block(snapshot)


def build_user_prompt(snapshot: MarketSnapshot) -> str:
    return f"""{asset_header(snapshot)}
{format_news_block(snapshot)}
{format_economic_calendar_block(snapshot)}

السعر: {snapshot.price}
حالة السوق: {snapshot.regime.regime.value}
التذبذب: {snapshot.regime.volatility_pct}%
بيانات قديمة: {snapshot.feed_stale}
مفتاح الأمان: {snapshot.kill_switch.status.value}
الوقت: {snapshot.timestamp.isoformat()}"""


def flatten_news_reasoning(output: NewsAgentLLMOutput) -> list[str]:
    """Merge extended news fields into reasoning for consensus display."""
    reasoning = list(output.reasoning)
    if output.asset_impacts:
        impacts = " | ".join(
            f"{asset}: {impact}" for asset, impact in output.asset_impacts.items()
        )
        reasoning.append(f"تأثير الأصول: {impacts}")
    reasoning.append(f"مستوى الخطر: {output.overall_risk_level}")
    if output.recommendation_ar:
        reasoning.append(f"التوصية: {output.recommendation_ar}")
    return reasoning[:15]
