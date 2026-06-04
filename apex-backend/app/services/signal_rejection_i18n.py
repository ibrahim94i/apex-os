"""Arabic labels for signal rejection / wait reasons."""

from __future__ import annotations

REJECTION_AR: dict[str, str] = {
    "safety_gate_long_trending_down": "رفض Safety Gate: شراء ممنوع — السوق في اتجاه هابط",
    "safety_gate_long_adx_extreme": "رفض Safety Gate: شراء ممنوع — ADX مرتفع جداً (تذبذب عنيف)",
    "safety_gate_long_below_ema200": "رفض Safety Gate: شراء ممنوع — السعر تحت EMA200",
    "safety_gate_short_trending_up": "رفض Safety Gate: بيع ممنوع — السوق في اتجاه صاعد",
    "safety_gate_short_adx_extreme": "رفض Safety Gate: بيع ممنوع — ADX مرتفع جداً (تذبذب عنيف)",
    "safety_gate_short_above_ema200": "رفض Safety Gate: بيع ممنوع — السعر فوق EMA200",
    "neutral_direction": "لا إشارة — توصية الوكلاء محايدة",
    "selectivity_wait": "انتظار — فلاتر انتقائية (ثقة أو RSI أو ATR)",
    "signal_suppressed": "انتظار — فترة بين الإشارات أو تغيير السعر غير كافٍ",
    "ranging_market_wait": "السوق جانبي — انتظر",
}


def rejection_reason_ar(code: str | None) -> str | None:
    if not code:
        return None
    return REJECTION_AR.get(code, f"مرفوض: {code}")
