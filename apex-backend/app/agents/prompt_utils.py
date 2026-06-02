"""Shared prompt helpers — asset-agnostic agent context."""

from app.config.assets import get_asset
from app.schemas.agent import MarketSnapshot

AGENT_JSON_SCHEMA = """{
  "direction": "LONG" | "SHORT" | "NEUTRAL",
  "confidence": 0.0-1.0,
  "reasoning": ["سبب 1 بالعربية", "سبب 2 بالعربية"]
}"""

AGENT_JSON_RULES = """قواعد إلزامية لجميع الأصول (BTCUSDT, XAUUSD, EURUSD):
- أعد JSON واحداً فقط في الجذر (root) بدون غلاف أو مفتاح إضافي.
- يجب أن يحتوي الجذر مباشرة على: direction, confidence, reasoning.
- confidence رقم بين 0.0 و 1.0 (مثال: 0.75 وليس 75).
- reasoning قائمة نصوص عربية (1–15 سبباً)."""


def asset_header(snapshot: MarketSnapshot) -> str:
    asset = get_asset(snapshot.symbol)
    name_ar = asset.display_name_ar if asset else snapshot.symbol
    return f"الأصل: {name_ar} ({snapshot.symbol})"
