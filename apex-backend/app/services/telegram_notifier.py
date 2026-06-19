"""Telegram alert notifications for trading signals and emergency warnings."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from app.agents.base_weights import STRONG_CONSENSUS_THRESHOLD
from app.config.assets import get_asset
from app.config import settings
from app.logging_config import logger
from app.schemas import RegimeType, SignalDirection, TradingSignalSchema
from app.schemas.agent import AgentConsensus, TeamDiscussionLLMOutput
from app.schemas.snr import SNRSnapshotSchema
from app.utils.price_zones import entry_zone_from_price

INSIDE_ZONE_MAX_DISPLAY_CONFIDENCE = 0.60
INSIDE_ZONE_WARNING_AR = "⚠️ السعر داخل منطقة دعم/مقاومة — تداول بحذر"
MACD_DIVERGENCE_WARNING_AR = "⚠️ تحذير — MACD يعارض الاتجاه (زخم ضعيف)"

BAGHDAD = ZoneInfo("Asia/Baghdad")

ASSET_AR = {
    "XAUUSD": "ذهب",
    "EURUSD": "يورو/دولار",
    "USDJPY": "دولار/ين",
    "GBPUSD": "جنيه/دولار",
    "BTCUSDT": "بيتكوين",
}
DIRECTION_AR = {SignalDirection.LONG: "شراء", SignalDirection.SHORT: "بيع"}
REGIME_AR = {
    RegimeType.TRENDING_UP: "اتجاه صاعد",
    RegimeType.TRENDING_DOWN: "اتجاه هابط",
    RegimeType.RANGING: "نطاق جانبي",
    RegimeType.VOLATILE: "تذبذب عالي",
    RegimeType.UNKNOWN: "غير محدد",
}

EMERGENCY_MESSAGES = {
    "market_turned_bullish": "⚠️ <b>تحذير طارئ</b>\nالسوق تحول للصعود — راجع صفقتك",
    "market_turned_bearish": "⚠️ <b>تحذير طارئ</b>\nالسوق تحول للهبوط — راجع صفقتك",
}


class TelegramNotifier:
    def __init__(self) -> None:
        self._base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    @property
    def enabled(self) -> bool:
        return bool(settings.telegram_bot_token and settings.telegram_chat_id)

    async def _send(self, text: str) -> bool:
        if not self.enabled:
            logger.warning("telegram_disabled")
            return False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base}/sendMessage",
                    json={
                        "chat_id": settings.telegram_chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )
                if resp.status_code != 200:
                    logger.error("telegram_send_failed", status=resp.status_code, body=resp.text[:200])
                    return False
                return True
        except Exception as exc:
            logger.error("telegram_error", error=str(exc))
            return False

    async def send_test_message(self) -> bool:
        now = datetime.now(BAGHDAD).strftime("%Y-%m-%d %H:%M")
        text = (
            "✅ <b>APEX OS v2.0</b>\n"
            "تم تشغيل النظام بنجاح.\n"
            f"🕐 {now} (توقيت العراق)\n"
            "سيتم إرسال الإشارات فور صدورها (ثقة ≥ 70%)."
        )
        return await self._send(text)

    async def send_emergency_position_warning(
        self,
        symbol: str,
        alert_type: str,
        confidence: float,
        open_direction: str,
        new_direction: str,
    ) -> bool:
        base = EMERGENCY_MESSAGES.get(alert_type)
        if not base:
            return False
        asset = ASSET_AR.get(symbol, symbol)
        dir_open = "بيع" if open_direction == "SHORT" else "شراء"
        dir_new = DIRECTION_AR.get(SignalDirection(new_direction), new_direction)
        text = (
            f"{base}\n\n"
            f"📌 الأصل: <b>{asset}</b>\n"
            f"📂 صفقة مفتوحة: <b>{dir_open}</b>\n"
            f"🔄 إشارة جديدة: <b>{dir_new}</b> — ثقة <b>{confidence * 100:.1f}%</b>\n"
            f"⏰ {datetime.now(BAGHDAD).strftime('%Y-%m-%d %H:%M')} (العراق)"
        )
        return await self._send(text)

    @staticmethod
    def _normalize_snr_state(snr_state: str | None) -> str:
        return (snr_state or "").lower().strip()

    @staticmethod
    def _display_confidence(collective_confidence: float, snr_state: str | None) -> float:
        """Cap displayed confidence at 60% when price is inside an SNR zone."""
        if TelegramNotifier._normalize_snr_state(snr_state) == "inside_zone":
            return min(collective_confidence, INSIDE_ZONE_MAX_DISPLAY_CONFIDENCE)
        return collective_confidence

    @staticmethod
    def _has_macd_divergence(degradation_reason: str | None) -> bool:
        return bool(degradation_reason and "MACD divergence" in degradation_reason)

    @staticmethod
    def _format_snr_levels(
        snr: SNRSnapshotSchema | None,
        entry_price: float,
        decimals: int,
    ) -> str:
        if snr is None:
            return ""
        lines = ["\n📊 مستويات SNR:"]
        if snr.resistance_1 is not None:
            pts = abs(snr.resistance_1 - entry_price)
            lines.append(
                f"🔴 مقاومة: <code>{snr.resistance_1:.{decimals}f}</code> "
                f"({pts:.{decimals}f} نقطة فوق الدخول)"
            )
        if snr.support_1 is not None:
            pts = abs(entry_price - snr.support_1)
            lines.append(
                f"🟢 دعم: <code>{snr.support_1:.{decimals}f}</code> "
                f"({pts:.{decimals}f} نقطة تحت الدخول)"
            )
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def _format_team_discussion(self, discussion: TeamDiscussionLLMOutput) -> str:
        lines = ["\n<b>📋 ملخص نقاش الفريق</b>"]
        if discussion.discussion_summary:
            lines.append("\n".join(f"• {s}" for s in discussion.discussion_summary[:5]))
        if discussion.agreements:
            lines.append("\n<b>✅ نقاط الاتفاق:</b>")
            lines.append("\n".join(f"• {a}" for a in discussion.agreements[:4]))
        if discussion.disagreements:
            lines.append("\n<b>⚡ نقاط الخلاف:</b>")
            lines.append("\n".join(f"• {d}" for d in discussion.disagreements[:4]))
        final = discussion.round3_final
        dir_ar = DIRECTION_AR.get(final.direction, final.direction.value)
        lines.append(f"\n<b>🏁 القرار النهائي:</b> {dir_ar} — ثقة {final.confidence * 100:.1f}%")
        if final.reasoning:
            lines.append("\n".join(f"• {r}" for r in final.reasoning[:3]))
        return "\n".join(lines)

    async def send_signal_alert(
        self,
        signal: TradingSignalSchema,
        market_status_ar: str | None = None,
        consensus: AgentConsensus | None = None,
        snr: SNRSnapshotSchema | None = None,
    ) -> bool:
        collective_confidence = (
            consensus.final_confidence if consensus is not None else signal.confidence
        )
        if collective_confidence < STRONG_CONSENSUS_THRESHOLD:
            return False

        asset_cfg = get_asset(signal.symbol)
        asset = ASSET_AR.get(signal.symbol, signal.symbol)
        direction = DIRECTION_AR.get(signal.direction, signal.direction.value)
        regime = REGIME_AR.get(signal.regime, signal.regime.value)
        ts = signal.timestamp.astimezone(BAGHDAD).strftime("%Y-%m-%d %H:%M")
        decimals = asset_cfg.price_decimals if asset_cfg else 2
        snr_state = self._normalize_snr_state(signal.snr_state)
        display_confidence = self._display_confidence(collective_confidence, signal.snr_state)

        if signal.entry_zone_low is not None and signal.entry_zone_high is not None:
            zone_low = signal.entry_zone_low
            zone_high = signal.entry_zone_high
        else:
            zone_low, zone_high, _ = entry_zone_from_price(signal.entry_price, decimals=decimals)

        text = (
            f"🚨 <b>إشارة APEX — {asset}</b>\n\n"
            f"📊 الاتجاه: <b>{direction}</b>\n"
        )
        if signal.snr_explain_ar:
            text += f"🎯 سبب الإشارة: <b>{signal.snr_explain_ar}</b>\n"
        text += (
            f"📈 الثقة الجماعية: <b>{display_confidence * 100:.1f}%</b>\n"
            f"📍 منطقة الدخول: <code>{zone_low}</code> – <code>{zone_high}</code>\n"
            f"🛑 وقف الخسارة: <code>{signal.stop_loss}</code>\n"
            f"✅ هدف الربح: <code>{signal.take_profit}</code>\n"
            f"📈 حالة السوق: {regime}\n"
            f"⚠️ <b>ادخل لما يكون سعر MetaTrader داخل المنطقة</b>\n"
        )
        text += self._format_snr_levels(snr, signal.entry_price, decimals)
        if snr_state == "inside_zone":
            text += f"\n{INSIDE_ZONE_WARNING_AR}\n"
        if self._has_macd_divergence(signal.degradation_reason):
            text += f"{MACD_DIVERGENCE_WARNING_AR}\n"
        if market_status_ar:
            text += f"🕐 الجلسة: {market_status_ar}\n"
        if consensus and consensus.team_discussion:
            text += self._format_team_discussion(consensus.team_discussion)
        elif consensus and consensus.discussion_summary_ar:
            text += "\n<b>📋 ملخص:</b>\n" + "\n".join(
                f"• {s}" for s in consensus.discussion_summary_ar[:5]
            )
        if consensus and consensus.llm_provider:
            text += f"\n🤖 النموذج: {consensus.llm_provider}"
        text += f"\n⏰ وقت الإشارة: {ts} (العراق)"

        sent = await self._send(text)
        if sent:
            logger.info(
                "telegram_signal_sent",
                symbol=signal.symbol,
                direction=signal.direction.value,
                confidence=collective_confidence,
                display_confidence=display_confidence,
                snr_state=snr_state or None,
                signal_confidence=signal.confidence,
            )
        return sent

    async def send_signal_rejection(
        self,
        symbol: str,
        direction: SignalDirection,
        reason_code: str,
        *,
        reason_ar: str | None = None,
        confidence: float | None = None,
    ) -> bool:
        from app.services.signal_rejection_i18n import (
            is_snr_soft_penalty_reason,
            rejection_reason_ar,
        )

        if is_snr_soft_penalty_reason(reason_code):
            return False

        asset = ASSET_AR.get(symbol, symbol)
        dir_ar = DIRECTION_AR.get(direction, direction.value)
        reason_text = reason_ar or rejection_reason_ar(reason_code) or reason_code
        text = (
            f"🚫 <b>رفض إشارة APEX — {asset}</b>\n\n"
            f"📊 الاتجاه المقترح: <b>{dir_ar}</b>\n"
        )
        if confidence is not None:
            text += f"📈 الثقة الجماعية: <b>{confidence * 100:.1f}%</b>\n"
        text += f"❌ السبب: <b>{reason_text}</b>\n"
        text += f"⏰ {datetime.now(BAGHDAD).strftime('%Y-%m-%d %H:%M')} (العراق)"
        sent = await self._send(text)
        if sent:
            logger.info(
                "telegram_signal_rejection_sent",
                symbol=symbol,
                direction=direction.value,
                reason=reason_code,
            )
        return sent

    async def send_open_trade_warning(
        self,
        symbol: str,
        trade_direction: str,
        detail_ar: str,
    ) -> bool:
        asset = ASSET_AR.get(symbol, symbol)
        dir_ar = "بيع" if trade_direction == "SHORT" else "شراء"
        text = (
            "⚠️ <b>تحذير — صفقتك مفتوحة</b>\n"
            f"{detail_ar}\n\n"
            f"📌 الأصل: <b>{asset}</b>\n"
            f"📂 الاتجاه: <b>{dir_ar}</b>\n"
            f"⏰ {datetime.now(BAGHDAD).strftime('%Y-%m-%d %H:%M')} (العراق)"
        )
        sent = await self._send(text)
        if sent:
            logger.info(
                "telegram_open_trade_warning_sent",
                symbol=symbol,
                direction=trade_direction,
            )
        return sent

    async def send_data_source_failover_alert(
        self,
        symbol: str,
        *,
        primary: str,
        fallback: str,
    ) -> bool:
        asset = ASSET_AR.get(symbol, symbol)
        fallback_ar = {
            "finnhub": "Finnhub",
            "frankfurter": "Frankfurter (ECB)",
            "binance": "Binance REST",
            "alphavantage": "Alpha Vantage",
            "metals_live": "Metals.live (ذهب)",
            "db": "قاعدة البيانات (آخر بيانات محفوظة)",
            "twelvedata": "TwelveData",
        }.get(fallback, fallback)
        primary_ar = {
            "twelvedata": "TwelveData",
            "finnhub": "Finnhub",
        }.get(primary, primary)
        text = (
            f"⚠️ <b>انقطاع مصدر البيانات</b>\n\n"
            f"📌 الأصل: <b>{asset}</b>\n"
            f"❌ المصدر الأساسي ({primary_ar}) غير متاح\n"
            f"🔄 التبديل التلقائي إلى: <b>{fallback_ar}</b>\n"
            f"⏰ {datetime.now(BAGHDAD).strftime('%Y-%m-%d %H:%M')} (العراق)"
        )
        return await self._send(text)

    async def send_data_source_recovery_alert(
        self,
        symbol: str,
        *,
        primary: str,
        fallback: str,
    ) -> bool:
        asset = ASSET_AR.get(symbol, symbol)
        primary_ar = {"twelvedata": "TwelveData", "finnhub": "Finnhub"}.get(primary, primary)
        text = (
            f"✅ <b>عودة مصدر البيانات</b>\n\n"
            f"📌 الأصل: <b>{asset}</b>\n"
            f"🔗 {primary_ar} يعمل مجدداً\n"
            f"⏰ {datetime.now(BAGHDAD).strftime('%Y-%m-%d %H:%M')} (العراق)"
        )
        return await self._send(text)


telegram_notifier = TelegramNotifier()
