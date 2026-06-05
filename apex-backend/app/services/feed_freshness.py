"""Feed poll freshness — use last successful poll time, not candle open time."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.config.assets import get_asset
from app.core.cache import get_feed_last_update
from app.services.market_hours import is_market_open
from app.utils.time_utils import compute_age_seconds, parse_utc_timestamp


def feed_poll_age_seconds(last_raw: dict[str, Any] | None) -> int | None:
    """Age since the feed last polled successfully (not candle bar open time)."""
    if not last_raw:
        return None
    ts_raw = last_raw.get("received_at") or last_raw.get("timestamp")
    if not ts_raw:
        return None
    return compute_age_seconds(parse_utc_timestamp(ts_raw))


def feed_staleness_limit_seconds(symbol: str) -> int:
    """Max seconds without a successful poll before the feed is stale."""
    asset = get_asset(symbol)
    poll_based = asset.poll_interval * 3 if asset else 0
    return max(settings.feed_staleness_limit_seconds, poll_based)


async def is_feed_poll_stale(symbol: str) -> bool:
    """True when market is open but no recent successful poll."""
    if not is_market_open(symbol):
        return False
    last_raw = await get_feed_last_update(symbol)
    age = feed_poll_age_seconds(last_raw)
    if age is None:
        return True
    return age > feed_staleness_limit_seconds(symbol)
