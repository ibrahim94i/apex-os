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
    "confidence_below_threshold": "لا إشارة — الثقة أقل من 70%",
    "min_risk_reward_not_met": "لا إشارة — نسبة المخاطرة/العائد غير كافية",
    "signal_build_failed": "لا إشارة — فشل بناء الإشارة",
    "selectivity_wait": "انتظار — فلاتر انتقائية (ثقة أو RSI أو ATR)",
    "signal_suppressed": "انتظار — فترة بين الإشارات أو تغيير السعر غير كافٍ",
    "ranging_market_wait": "السوق جانبي — انتظر",
    "economic_calendar_pre_event": "رفض Safety Gate: حدث اقتصادي عالي التأثير خلال 30 دقيقة",
    "economic_calendar_post_event": "رفض Safety Gate: انتظار 15 دقيقة بعد صدور حدث اقتصادي",
    "snr_no_trade_zone_support": "انتظار — السعر داخل منطقة SNR (±0.25%)",
    "snr_no_trade_zone_resistance": "انتظار — السعر داخل منطقة SNR (±0.25%)",
    "snr_in_s1_zone": "انتظار — السعر داخل منطقة S1 (±0.25%)",
    "snr_in_s2_zone": "انتظار — السعر داخل منطقة S2 (±0.25%)",
    "snr_in_s3_zone": "انتظار — السعر داخل منطقة S3 (±0.25%)",
    "snr_in_r1_zone": "انتظار — السعر داخل منطقة R1 (±0.25%)",
    "snr_in_r2_zone": "انتظار — السعر داخل منطقة R2 (±0.25%)",
    "snr_in_r3_zone": "انتظار — السعر داخل منطقة R3 (±0.25%)",
    "snr_in_level_zone": "انتظار — السعر داخل منطقة SNR (±0.25%)",
}


def rejection_reason_ar(code: str | None) -> str | None:
    if not code:
        return None
    return REJECTION_AR.get(code, f"مرفوض: {code}")
