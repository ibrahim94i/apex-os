"""Professional signal emission — hourly continuous signals without cooldown blocking."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from app.config import settings
from app.config.assets import get_asset
from app.core.cache import get_latest_signal


async def should_emit_new_signal(symbol: str, entry_price: float) -> tuple[bool, str | None]:
    """
    Return (allowed, rejection_reason).

    Continuous signal mode: new closed-bar signals may emit every hour.
    Previous active signals do NOT block new emissions.
    Only blocks duplicate signals within the same hour bucket or insufficient price move.
    """
    last = await get_latest_signal(symbol)
    if not last:
        return True, None

    ts = last["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    interval = timedelta(hours=settings.signal_emission_interval_hours)
    if datetime.now(timezone.utc) - ts < interval:
        return False, "hourly_interval_not_elapsed"

    asset = get_asset(symbol)
    min_move = asset.min_price_move if asset else None
    if min_move is not None:
        last_entry = float(last.get("entry_price", entry_price))
        if abs(entry_price - last_entry) < min_move:
            return False, "insufficient_price_move"

    return True, None
