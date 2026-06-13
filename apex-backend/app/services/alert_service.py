"""In-app alert system — WebSocket push with deduplication."""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from app.core.redis_client import cache_get, cache_set
from app.websocket.manager import manager

AlertSound = Literal["alert", "warning", "critical"]


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    HIGH_CONFIDENCE = "high_confidence"
    KILL_SWITCH = "kill_switch"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    NEW_SIGNAL = "new_signal"


class Alert(BaseModel):
    id: str
    type: AlertType
    severity: AlertSeverity
    title_ar: str
    message_ar: str
    symbol: str | None = None
    timestamp: datetime
    fullscreen: bool = False
    play_sound: AlertSound = "alert"
    overlay_variant: str | None = None  # red | yellow | null


class AlertService:
    _counter = 0

    async def notify_new_signal(
        self, symbol: str, direction: str, confidence: float
    ) -> Alert:
        dir_ar = {"LONG": "شراء", "SHORT": "بيع", "NEUTRAL": "محايد"}
        high = confidence > 0.75
        dedup_key = f"new_signal:{symbol}:{direction}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
        if not await self._should_send(dedup_key, ttl=3600):
            return self._make_alert(
                AlertType.NEW_SIGNAL,
                AlertSeverity.INFO,
                "",
                "",
                symbol=symbol,
            )

        alert = self._make_alert(
            AlertType.NEW_SIGNAL if not high else AlertType.HIGH_CONFIDENCE,
            AlertSeverity.CRITICAL if high else AlertSeverity.INFO,
            "إشارة عالية الثقة" if high else "إشارة جديدة",
            f"{symbol}: {dir_ar.get(direction, direction)} — ثقة {(confidence * 100):.0f}%",
            symbol=symbol,
            fullscreen=high,
            play_sound="critical" if high else "alert",
            overlay_variant="red" if high else None,
        )
        if alert.title_ar:
            await self._push(alert)
        return alert

    async def check_high_confidence(
        self, symbol: str, direction: str, confidence: float
    ) -> Alert | None:
        """Legacy hook — high-confidence alerts are sent via notify_new_signal."""
        if confidence <= 0.75:
            return None
        return None

    async def check_kill_switch(self, active: bool, reason: str | None) -> Alert | None:
        if not active:
            await self._clear_dedup("kill_switch:active")
            return None
        if not await self._should_send("kill_switch:active", ttl=86400):
            return None
        alert = self._make_alert(
            AlertType.KILL_SWITCH,
            AlertSeverity.CRITICAL,
            "تحذير: مفتاح الأمان نشط",
            reason or "تم تفعيل مفتاح الأمان — التداول متوقف",
            fullscreen=True,
            play_sound="critical",
            overlay_variant="red",
        )
        await self._push(alert)
        return alert

    async def check_consecutive_losses(self, count: int) -> Alert | None:
        if count < 3:
            return None
        dedup_key = f"consecutive_losses:{count // 3}"
        if not await self._should_send(dedup_key, ttl=7200):
            return None
        alert = self._make_alert(
            AlertType.CONSECUTIVE_LOSSES,
            AlertSeverity.WARNING,
            "تحذير: خسائر متتالية",
            f"تم تسجيل {count} خسائر متتالية — راجع استراتيجيتك",
            fullscreen=True,
            play_sound="warning",
            overlay_variant="yellow",
        )
        await self._push(alert)
        return alert

    def _make_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title_ar: str,
        message_ar: str,
        symbol: str | None = None,
        fullscreen: bool = False,
        play_sound: AlertSound = "alert",
        overlay_variant: str | None = None,
    ) -> Alert:
        AlertService._counter += 1
        return Alert(
            id=f"alert-{AlertService._counter}-{int(datetime.now(timezone.utc).timestamp())}",
            type=alert_type,
            severity=severity,
            title_ar=title_ar,
            message_ar=message_ar,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            fullscreen=fullscreen,
            play_sound=play_sound,
            overlay_variant=overlay_variant,
        )

    async def _should_send(self, key: str, ttl: int = 3600) -> bool:
        redis_key = f"apex:alert_dedup:{key}"
        try:
            if await cache_get(redis_key):
                return False
            await cache_set(redis_key, {"sent": True}, ttl=ttl)
        except Exception:
            return True
        return True

    async def _clear_dedup(self, key: str) -> None:
        from app.core.redis_client import cache_delete

        try:
            await cache_delete(f"apex:alert_dedup:{key}")
        except Exception:
            return None

    async def _push(self, alert: Alert) -> None:
        await manager.broadcast({"type": "alert", "data": alert.model_dump(mode="json")})


alert_service = AlertService()
