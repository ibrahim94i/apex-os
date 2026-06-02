"""Telegram alert notifications for trading signals."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.logging_config import logger
from app.schemas import RegimeType, SignalDirection, TradingSignalSchema

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

    async def send_signal_alert(
        self,
        signal: TradingSignalSchema,
        market_status_ar: str | None = None,
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
        text += f"⏰ وقت الإشارة: {ts} (العراق)"

        return await self._send(text)


telegram_notifier = TelegramNotifier()
