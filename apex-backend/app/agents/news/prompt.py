"""Prompts for News Agent."""

from app.agents.news.calendar_format import format_economic_calendar_block
from app.agents.prompt_utils import AGENT_JSON_RULES, AGENT_JSON_SCHEMA, asset_header
from app.schemas.agent import MarketSnapshot

SYSTEM_PROMPT = f"""أنت وكيل أخبار macro متخصص في تقييم تأثير الأحداث على التداول.
حلل السياق لأي أصل (BTCUSDT, XAUUSD, EURUSD, USDJPY, GBPUSD) وأعد JSON فقط:
{AGENT_JSON_SCHEMA}
{AGENT_JSON_RULES}
استخدم عناوين Finnhub والتقويم الاقتصادي المرفق — اربط كل خبر/حدث بتأثيره على الأصل.
إن وُجد حدث high impact خلال 60 دقيقة: اذكر تحذيراً صريحاً في reasoning ويُفضّل NEUTRAL.
إذا كانت البيانات قديمة أو التذبذب عالياً، كن حذراً."""


def format_finnhub_news_block(snapshot: MarketSnapshot) -> str:
    if not snapshot.news_headlines:
        return "آخر الأخبار الاقتصادية (Finnhub): غير متوفرة — اعتمد على السياق العام فقط"
    lines = ["آخر الأخبار الاقتصادية (Finnhub):"]
    for idx, item in enumerate(snapshot.news_headlines[:5], start=1):
        when = (
            item.published_at.strftime("%Y-%m-%d %H:%M UTC")
            if item.published_at
            else "—"
        )
        lines.append(f"{idx}. [{item.source or 'Finnhub'}] {item.headline} ({when})")
        if item.summary:
            lines.append(f"   ملخص: {item.summary[:280]}")
    return "\n".join(lines)


def build_user_prompt(snapshot: MarketSnapshot) -> str:
    return f"""{asset_header(snapshot)}
{format_finnhub_news_block(snapshot)}
{format_economic_calendar_block(snapshot)}

السعر: {snapshot.price}
حالة السوق: {snapshot.regime.regime.value}
التذبذب: {snapshot.regime.volatility_pct}%
بيانات قديمة: {snapshot.feed_stale}
مفتاح الأمان: {snapshot.kill_switch.status.value}
الوقت: {snapshot.timestamp.isoformat()}"""
