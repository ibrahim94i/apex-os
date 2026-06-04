"""Format candlestick patterns for LLM prompts."""

from app.schemas.agent import CandlestickPatternSchema, MarketSnapshot

_SIGNAL_AR = {
    "bullish": "صعودي",
    "bearish": "هبوطي",
    "neutral": "محايد",
}


def format_candlestick_block(patterns: list[CandlestickPatternSchema]) -> str:
    if not patterns:
        return "\nأنماط الشمعات (H1): لا أنماط بارزة على آخر الشموع المغلقة."

    lines: list[str] = []
    for p in patterns:
        when = "آخر شمعة مغلقة" if p.bar_offset == 0 else f"قبل {p.bar_offset} شمعة"
        lines.append(
            f"- {p.name_ar} ({p.pattern}): إشارة {_SIGNAL_AR.get(p.signal, p.signal)} "
            f"| قوة {p.strength:.0%} | {when} | مصدر {p.source}"
        )
    return "\nأنماط الشمعات (H1):\n" + "\n".join(lines)


def candlestick_block_from_snapshot(snapshot: MarketSnapshot) -> str:
    return format_candlestick_block(snapshot.candlestick_patterns)
