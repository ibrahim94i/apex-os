"""Global rate limiter for TwelveData API — avoids 429 with multiple assets."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

_lock = asyncio.Lock()
_last_request_at: float = 0.0
_recovery_paused_until: datetime | None = None


def record_twelvedata_429() -> None:
    """Pause feed recovery after TwelveData rate-limits us."""
    global _recovery_paused_until
    pause = settings.twelvedata_429_recovery_pause_seconds
    _recovery_paused_until = datetime.now(timezone.utc) + timedelta(seconds=pause)


def is_feed_recovery_paused() -> bool:
    """True while feed recovery is paused due to a recent TwelveData 429."""
    if _recovery_paused_until is None:
        return False
    return datetime.now(timezone.utc) < _recovery_paused_until


def feed_recovery_pause_remaining_seconds() -> int | None:
    if not is_feed_recovery_paused() or _recovery_paused_until is None:
        return None
    remaining = int((_recovery_paused_until - datetime.now(timezone.utc)).total_seconds())
    return max(remaining, 0)


def clear_feed_recovery_pause() -> None:
    """Test helper — reset 429 recovery pause."""
    global _recovery_paused_until
    _recovery_paused_until = None


async def throttled_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict,
) -> httpx.Response:
    global _last_request_at
    min_gap = settings.twelvedata_min_gap_seconds
    async with _lock:
        now = time.monotonic()
        wait = min_gap - (now - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        response = await client.get(url, params=params)
        _last_request_at = time.monotonic()
        if response.status_code == 429:
            record_twelvedata_429()
        return response
