"""Arabic labels for signal rejection / wait reasons."""

from __future__ import annotations

SNR_INSIDE_ZONE_WARNING_AR = "تحذير — السعر داخل منطقة SNR"

# Legacy hard-block SNR codes — SNR is soft penalty only; never show as rejection.
SNR_SOFT_PENALTY_CODES: frozenset[str] = frozenset(
    {
        "SNR Zone Block",
        "snr_awaiting_breakout",
        "snr_in_level_zone",
        "snr_no_trade_zone_support",
        "snr_no_trade_zone_resistance",
        "snr_in_s1_zone",
        "snr_in_s2_zone",
        "snr_in_s3_zone",
        "snr_in_r1_zone",
        "snr_in_r2_zone",
        "snr_in_r3_zone",
        "WAIT",
    }
)

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
    "no_agent_consensus": "لا قرار — بيانات الوكلاء غير متوفرة",
    "invalid_trade_levels": "رفض — مستويات SL/TP غير صالحة (المسافة أو R:R)",
}


def is_snr_soft_penalty_reason(code: str | None) -> bool:
    if not code:
        return False
    if code in SNR_SOFT_PENALTY_CODES:
        return True
    return code.startswith("snr_in_") or code.startswith("snr_no_trade")


def is_snr_hard_block_message(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return (
        "فيتو" in text
        or "snr zone block" in lowered
        or "wait = no_trade" in lowered
        or "no_trade" in lowered and "snr" in lowered
    )


def rejection_reason_ar(code: str | None) -> str | None:
    if not code:
        return None
    if is_snr_soft_penalty_reason(code):
        return None
    return REJECTION_AR.get(code, f"مرفوض: {code}")


def normalize_snr_consensus_fields(
    *,
    rejection_reason: str | None,
    rejection_reason_ar: str | None,
    snr_warning_ar: str | None,
    final_decision: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """
    Ensure SNR soft penalty never appears as a hard rejection in UI/Telegram.
    Maps legacy veto messages to snr_warning_ar only.
    """
    warning = snr_warning_ar

    if is_snr_soft_penalty_reason(rejection_reason):
        warning = warning or SNR_INSIDE_ZONE_WARNING_AR
        rejection_reason = None
        rejection_reason_ar = None
    elif is_snr_hard_block_message(rejection_reason_ar):
        warning = warning or SNR_INSIDE_ZONE_WARNING_AR
        rejection_reason = None
        rejection_reason_ar = None

    if final_decision in ("BUY", "SELL") and warning:
        rejection_reason = None
        rejection_reason_ar = None

    return rejection_reason, rejection_reason_ar, warning
