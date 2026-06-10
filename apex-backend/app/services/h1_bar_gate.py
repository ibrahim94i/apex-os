"""Gate heavy H1 pipeline work to once per closed hourly bar."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.redis_client import cache_get, cache_set

_H1_LAST_PROCESSED_KEY = "apex:h1_last_processed:{symbol}"


def normalize_h1_bucket(bar_timestamp: str | datetime) -> str:
    if isinstance(bar_timestamp, str):
        dt = datetime.fromisoformat(bar_timestamp.replace("Z", "+00:00"))
    else:
        dt = bar_timestamp
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    hour = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return hour.isoformat()


async def should_run_h1_pipeline(symbol: str, bar_timestamp: str | datetime) -> bool:
    """True when this hourly bar has not yet triggered the H1 agent/signal path."""
    bucket = normalize_h1_bucket(bar_timestamp)
    key = _H1_LAST_PROCESSED_KEY.format(symbol=symbol)
    last = await cache_get(key)
    if last and last.get("bucket") == bucket:
        return False
    return True


async def mark_h1_pipeline_processed(symbol: str, bar_timestamp: str | datetime) -> None:
    bucket = normalize_h1_bucket(bar_timestamp)
    key = _H1_LAST_PROCESSED_KEY.format(symbol=symbol)
    await cache_set(key, {"bucket": bucket}, ttl=7200)
