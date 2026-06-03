"""Telegram alert notifications for trading signals and emergency warnings."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.logging_config import logger
from app.schemas import RegimeType, SignalDirection, TradingSignalSchema
from app.schemas.agent import AgentConsensus, TeamDiscussionLLMOutput

BAGHDAD = ZoneInfo("Asia/Baghdad")

ASSET_AR = {"XAUUSD": "ذهب", "BTCUSDT": "بيتكوين", "EURUSD": "يورو/دولار"}
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
    ) -> bool:
        if signal.confidence < 0.70:
            return False

        asset = ASSET_AR.get(signal.symbol, signal.symbol)
        direction = DIRECTION_AR.get(signal.direction, signal.direction.value)
        regime = REGIME_AR.get(signal.regime, signal.regime.value)
        ts = signal.timestamp.astimezone(BAGHDAD).strftime("%Y-%m-%d %H:%M")

        text = (
            f"🚨 <b>إشارة APEX — {asset}</b>\n\n"
            f"📊 الاتجاه: <b>{direction}</b>\n"
            f"🎯 الثقة: <b>{signal.confidence * 100:.1f}%</b>\n"
            f"💰 الدخول: <code>{signal.entry_price}</code>\n"
            f"🛑 وقف الخسارة: <code>{signal.stop_loss}</code>\n"
            f"✅ هدف الربح: <code>{signal.take_profit}</code>\n"
            f"📈 حالة السوق: {regime}\n"
        )
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

        return await self._send(text)


telegram_notifier = TelegramNotifier()
