"""Combined multi-agent prompt — one Groq request for all three agents."""

from app.agents.market_analyst.prompt import build_user_prompt as build_market_prompt
from app.agents.news.prompt import build_user_prompt as build_news_prompt
from app.agents.risk.prompt import build_user_prompt as build_risk_prompt
from app.agents.prompt_utils import AGENT_JSON_RULES, asset_header
from app.schemas.agent import MarketSnapshot

SYSTEM_PROMPT = f"""أنت نظام APEX متعدد الوكلاء. حلّل السوق مرة واحدة وأعد JSON واحداً يحتوي ثلاثة وكلاء:
{{
  "market_analyst": {{ "direction": "LONG"|"SHORT"|"NEUTRAL", "confidence": 0.0-1.0, "reasoning": ["..."] }},
  "risk": {{ "direction": "LONG"|"SHORT"|"NEUTRAL", "confidence": 0.0-1.0, "reasoning": ["..."] }},
  "news": {{ "direction": "LONG"|"SHORT"|"NEUTRAL", "confidence": 0.0-1.0, "reasoning": ["..."] }}
}}
{AGENT_JSON_RULES}
- محلل السوق: تحليل فني (RSI, MACD, EMA, ADX)
- وكيل المخاطر: رصيد الحساب، مفتاح الأمان، ATR، خسائر متتالية
- وكيل الأخبار: عناوين Finnhub الاقتصادية المرفقة، macro، تذبذب
إذا مفتاح الأمان نشط → risk.direction = NEUTRAL
جميع reasoning بالعربية (1-5 أسباب لكل وكيل)."""


def build_combined_user_prompt(snapshot: MarketSnapshot) -> str:
    return f"""=== طلب تحليل موحّد ===
{asset_header(snapshot)}

--- محلل السوق ---
{build_market_prompt(snapshot)}

--- وكيل المخاطر ---
{build_risk_prompt(snapshot)}

--- وكيل الأخبار ---
{build_news_prompt(snapshot)}

أعد JSON واحداً بالمفاتيح: market_analyst, risk, news"""
