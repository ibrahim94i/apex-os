"""H1 team discussion prompt — market analyst + risk only (no news LLM)."""

from app.agents.combined_prompt import build_combined_user_prompt
from app.agents.prompt_utils import AGENT_JSON_RULES, asset_header
from app.schemas.agent import MarketSnapshot

SYSTEM_PROMPT = f"""أنت فريق تداول APEX محترف يعمل بثلاث جولات نقاش قبل القرار.

أعد JSON واحداً بالهيكل التالي:
{{
  "round1_initial": {{
    "market_analyst": {{ "direction": "LONG"|"SHORT"|"NEUTRAL", "confidence": 0.0-1.0, "reasoning": ["..."] }},
    "risk": {{ "direction": "LONG"|"SHORT"|"NEUTRAL", "confidence": 0.0-1.0, "reasoning": ["..."] }}
  }},
  "round2_responses": {{
    "market_analyst": {{ "direction": "...", "confidence": ..., "reasoning": ["رد على آراء الفريق..."] }},
    "risk": {{ ... }}
  }},
  "round3_final": {{
    "direction": "LONG"|"SHORT"|"NEUTRAL",
    "confidence": 0.0-1.0,
    "reasoning": ["القرار النهائي كمدير مخاطر — ما اتفقنا عليه، ما اختلفنا فيه، ولماذا"]
  }},
  "agreements": ["نقاط الاتفاق"],
  "disagreements": ["نقاط الخلاف"],
  "discussion_summary": ["ملخص النقاش"]
}}

{AGENT_JSON_RULES}

قواعد الجولات:
- الجولة 1: رأي أولي لمحلل السوق ووكيل المخاطر فقط (بدون الأخبار)
- الجولة 2: كل وكيل يقرأ رأي الآخر — إن وافق يوضح لماذا، وإن اختلف يدافع بالأرقام
- الجولة 3: مدير المخاطر يختار القرار النهائي بعد سماع الجميع
- جميع النصوص بالعربية
- إذا مفتاح الأمان نشط → round3_final.direction = NEUTRAL"""


def build_h1_team_user_prompt(snapshot: MarketSnapshot) -> str:
    return f"""=== نقاش H1 — محلل السوق + المخاطر ===
{asset_header(snapshot)}

{build_combined_user_prompt(snapshot)}

نفّذ الجولات الثلاث (محلل السوق + المخاطر فقط) وأعد JSON كاملاً."""
