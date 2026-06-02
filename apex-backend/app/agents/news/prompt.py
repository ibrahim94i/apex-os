"""Prompts for News Agent."""

from app.agents.prompt_utils import AGENT_JSON_RULES, AGENT_JSON_SCHEMA, asset_header
from app.schemas.agent import MarketSnapshot

SYSTEM_PROMPT = f"""أنت وكيل أخبار macro متخصص في تقييم تأثير الأحداث على التداول.
حلل السياق لأي أصل (BTCUSDT, XAUUSD, EURUSD) وأعد JSON فقط:
{AGENT_JSON_SCHEMA}
{AGENT_JSON_RULES}
إذا كانت البيانات قديمة أو التذبذب عالياً، كن حذراً."""


def build_user_prompt(snapshot: MarketSnapshot) -> str:
    return f"""{asset_header(snapshot)}
السعر: {snapshot.price}
حالة السوق: {snapshot.regime.regime.value}
التذبذب: {snapshot.regime.volatility_pct}%
بيانات قديمة: {snapshot.feed_stale}
مفتاح الأمان: {snapshot.kill_switch.status.value}
الوقت: {snapshot.timestamp.isoformat()}"""
