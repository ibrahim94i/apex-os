"""Global rate limiter for TwelveData API — avoids 429 with multiple assets."""

from __future__ import annotations

import asyncio
import time

import httpx

from app.config import settings

_lock = asyncio.Lock()
_last_request_at: float = 0.0


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
        return response
