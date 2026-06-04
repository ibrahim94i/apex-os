"""Prompts for Market Analyst Agent."""

from app.agents.market_analyst.candlestick_format import candlestick_block_from_snapshot
from app.agents.prompt_utils import AGENT_JSON_RULES, AGENT_JSON_SCHEMA, asset_header
from app.schemas.agent import MarketSnapshot

SYSTEM_PROMPT = f"""أنت محلل سوق مؤسسي متخصص في التحليل الفني وأنماط الشمعات.
حلل المؤشرات وأنماط الشمعات (دوجي، مطرقة، ابتلاع، نجمة الصباح/المساء، نجم هابط) لأي أصل وأعد JSON فقط:
{AGENT_JSON_SCHEMA}
{AGENT_JSON_RULES}
- إن وُجدت أنماط شمعات صعودية/هبوطية، اذكرها ضمن reasoning.
كن موضوعياً ومختصراً (2-5 أسباب)."""


def build_user_prompt(snapshot: MarketSnapshot) -> str:
    ind = snapshot.indicators
    regime = snapshot.regime
    patterns_text = ""
    if snapshot.memory_patterns:
        lines = []
        for p in snapshot.memory_patterns[:5]:
            regime_ar = {
                "TRENDING_UP": "اتجاه صاعد",
                "TRENDING_DOWN": "اتجاه هابط",
                "RANGING": "سوق جانبي",
                "VOLATILE": "تذبذب عالي",
            }.get(p.get("regime", ""), p.get("regime"))
            tod_ar = {
                "morning": "صباحاً",
                "afternoon": "ظهراً",
                "evening": "مساءً",
                "night": "ليلاً",
            }.get(p.get("time_of_day", ""), p.get("time_of_day"))
            lines.append(
                f"- {regime_ar} / {tod_ar}: فوز {p.get('win_rate', 0):.0%}, "
                f"RR {p.get('avg_rr', 0):.1f}, عينات {p.get('sample_count', 0)}"
            )
        patterns_text = "\nأنماط الذاكرة التاريخية (أفضل 5):\n" + "\n".join(lines)

    return f"""{asset_header(snapshot)}
السعر: {snapshot.price}
RSI: {ind.rsi}
MACD: {ind.macd}, Signal: {ind.macd_signal}
EMA9: {ind.ema_9}, EMA21: {ind.ema_21}, EMA50: {ind.ema_50}, EMA200: {ind.ema_200}
ATR: {ind.atr}, ADX: {ind.adx}
حالة السوق: {regime.regime.value}
ثقة النظام: {regime.confidence}
التذبذب: {regime.volatility_pct}%
{candlestick_block_from_snapshot(snapshot)}{patterns_text}"""
