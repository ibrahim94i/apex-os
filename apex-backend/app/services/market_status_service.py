"""Build live market status with countdowns."""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.config.assets import ASSETS, get_asset
from app.core.cache import get_latest_signal
from app.schemas.market import MarketStatusSchema
from app.services.market_hours import (
    SCHEDULE_LABELS,
    is_market_open,
    next_market_open,
    next_signal_opportunity,
)


def _seconds_until(target: datetime | None, now: datetime) -> int | None:
    if target is None:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    delta = int((target - now).total_seconds())
    return max(delta, 0)


async def build_market_status(symbol: str, at: datetime | None = None) -> MarketStatusSchema:
    now = at or datetime.now(timezone.utc)
    open_now = is_market_open(symbol, now)
    schedule = SCHEDULE_LABELS.get(symbol, "")

    next_open = next_market_open(symbol, now)
    seconds_open = _seconds_until(next_open, now) if not open_now else None

    last_signal_at: datetime | None = None
    last_data = await get_latest_signal(symbol)
    if last_data and last_data.get("timestamp"):
        ts = last_data["timestamp"]
        last_signal_at = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

    next_signal = next_signal_opportunity(
        symbol,
        last_signal_at,
        settings.signal_cooldown_hours,
        now,
    )
    seconds_signal = _seconds_until(next_signal, now) if open_now else None

    return MarketStatusSchema(
        symbol=symbol,
        is_open=open_now,
        schedule_ar=schedule,
        next_open_at=next_open,
        next_signal_at=next_signal,
        seconds_until_open=seconds_open,
        seconds_until_next_signal=seconds_signal,
    )


async def build_all_market_statuses() -> dict[str, MarketStatusSchema]:
    result: dict[str, MarketStatusSchema] = {}
    for symbol in ASSETS:
        result[symbol] = await build_market_status(symbol)
    return result
