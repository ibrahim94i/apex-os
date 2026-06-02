"""Feed connection status — Redis-backed for dashboard display."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.core.redis_client import cache_get, cache_set

STATUS_TTL = 3600


class FeedConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


STATUS_AR: dict[str, str] = {
    FeedConnectionState.CONNECTED.value: "متصل",
    FeedConnectionState.DISCONNECTED.value: "منقطع",
    FeedConnectionState.RECONNECTING.value: "يعيد الاتصال",
}


def _key(symbol: str) -> str:
    return f"apex:feed_status:{symbol}"


async def set_feed_status(
    symbol: str,
    status: FeedConnectionState,
    *,
    last_update: datetime | None = None,
    age_seconds: int | None = None,
    consecutive_failures: int = 0,
    detail: str | None = None,
) -> None:
    payload = {
        "symbol": symbol,
        "status": status.value,
        "status_ar": STATUS_AR[status.value],
        "last_update": (last_update or datetime.now(timezone.utc)).isoformat(),
        "age_seconds": age_seconds,
        "consecutive_failures": consecutive_failures,
        "detail": detail,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await cache_set(_key(symbol), payload, ttl=STATUS_TTL)


async def get_feed_status(symbol: str) -> dict[str, Any] | None:
    return await cache_get(_key(symbol))


async def get_all_feed_statuses(symbols: list[str]) -> dict[str, dict[str, Any]]:
    now = datetime.now(timezone.utc)
    out: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        data = await get_feed_status(sym)
        if data:
            if data.get("last_update") and data.get("age_seconds") is None:
                try:
                    ts = datetime.fromisoformat(str(data["last_update"]).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    data["age_seconds"] = int((now - ts).total_seconds())
                except (TypeError, ValueError):
                    pass
            out[sym] = data
        else:
            out[sym] = {
                "symbol": sym,
                "status": FeedConnectionState.DISCONNECTED.value,
                "status_ar": STATUS_AR[FeedConnectionState.DISCONNECTED.value],
                "last_update": None,
                "age_seconds": None,
                "consecutive_failures": 0,
            }
    return out
