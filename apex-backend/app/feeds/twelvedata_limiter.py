"""Global rate limiter and daily credit budget for TwelveData API."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.core.redis_client import cache_delete, cache_get, cache_set
from app.logging_config import logger

_lock = asyncio.Lock()
_credit_lock = asyncio.Lock()
_last_request_at: float = 0.0
_recovery_paused_until: datetime | None = None


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _credits_redis_key(day: str | None = None) -> str:
    return f"twelvedata_credits:{day or _utc_day()}"


def _redis_ttl_seconds() -> int:
    """Keep today's key through the next UTC day, then expire."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds()) + 86400


@dataclass
class _CreditState:
    day: str = ""
    used: int = 0
    exhausted: bool = False
    loaded: bool = False


_credit_state = _CreditState()


async def _ensure_credits_loaded() -> None:
    """Load today's credit counter from Redis (survives restarts)."""
    global _credit_state
    today = _utc_day()
    if _credit_state.loaded and _credit_state.day == today:
        return

    raw = await cache_get(_credits_redis_key(today))
    if raw:
        _credit_state = _CreditState(
            day=today,
            used=int(raw.get("used", 0)),
            exhausted=bool(raw.get("exhausted", False)),
            loaded=True,
        )
        return

    _credit_state = _CreditState(day=today, used=0, exhausted=False, loaded=True)


async def _persist_credits() -> None:
    await cache_set(
        _credits_redis_key(_credit_state.day),
        {"used": _credit_state.used, "exhausted": _credit_state.exhausted},
        ttl=_redis_ttl_seconds(),
    )


async def record_twelvedata_429(response_body: dict | None = None) -> None:
    """Pause feed recovery after TwelveData rate-limits us."""
    global _recovery_paused_until
    pause = settings.twelvedata_429_recovery_pause_seconds
    _recovery_paused_until = datetime.now(timezone.utc) + timedelta(seconds=pause)
    if _is_credits_exhausted_message(response_body):
        await mark_credits_exhausted()


async def mark_credits_exhausted() -> None:
    async with _credit_lock:
        await _ensure_credits_loaded()
        _credit_state.exhausted = True
        await _persist_credits()
    logger.warning(
        "twelvedata_credits_exhausted",
        used=_credit_state.used,
        limit=settings.twelvedata_daily_credit_limit,
        day=_credit_state.day,
    )


async def record_credits_used(credits: int, *, reason: str) -> None:
    """Track estimated TwelveData credits consumed (1 credit per data point)."""
    if credits <= 0:
        return

    async with _credit_lock:
        await _ensure_credits_loaded()
        _credit_state.used += credits
        limit = settings.twelvedata_daily_credit_limit
        if _credit_state.used >= limit:
            _credit_state.exhausted = True
        await _persist_credits()
        used_today = _credit_state.used
        exhausted = _credit_state.exhausted

    logger.info(
        "twelvedata_credits_used",
        credits=credits,
        used_today=used_today,
        limit=limit,
        remaining=max(limit - used_today, 0),
        reason=reason,
    )


def estimate_request_credits(params: dict) -> int:
    raw = params.get("outputsize", 1)
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1


async def credits_remaining_today() -> int:
    await _ensure_credits_loaded()
    return max(settings.twelvedata_daily_credit_limit - _credit_state.used, 0)


async def is_credits_exhausted() -> bool:
    await _ensure_credits_loaded()
    if _credit_state.exhausted:
        return True
    return _credit_state.used >= settings.twelvedata_daily_credit_limit


async def can_afford_credits(credits: int) -> bool:
    await _ensure_credits_loaded()
    if _credit_state.exhausted:
        return False
    return _credit_state.used + credits <= settings.twelvedata_daily_credit_limit


async def should_skip_twelvedata_api(credits: int = 1) -> bool:
    """Skip API when credits are gone or a recent 429 pause is active."""
    if await is_credits_exhausted():
        return True
    if not await can_afford_credits(credits):
        return True
    return False


async def get_credit_usage_report() -> dict[str, int | str | bool]:
    await _ensure_credits_loaded()
    limit = settings.twelvedata_daily_credit_limit
    used = _credit_state.used
    return {
        "day": _credit_state.day,
        "used": used,
        "limit": limit,
        "remaining": max(limit - used, 0),
        "exhausted": await is_credits_exhausted(),
        "recovery_paused": is_feed_recovery_paused(),
    }


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


async def clear_credit_tracking() -> None:
    """Test helper — reset in-memory and Redis credit counters for today."""
    global _credit_state
    today = _utc_day()
    _credit_state = _CreditState()
    await cache_delete(_credits_redis_key(today))


async def reset_twelvedata_credits() -> dict[str, int | str | bool]:
    """Admin reset — clear stuck exhausted flag and 429 recovery pause for today."""
    global _credit_state
    today = _utc_day()
    redis_key = _credits_redis_key(today)

    async with _credit_lock:
        await cache_delete(redis_key)
        clear_feed_recovery_pause()
        _credit_state = _CreditState(day=today, used=0, exhausted=False, loaded=True)
        await _persist_credits()

    report = await get_credit_usage_report()
    logger.info(
        "twelvedata_credits_reset",
        redis_key=redis_key,
        exhausted=report["exhausted"],
        recovery_paused=report["recovery_paused"],
    )
    return report


def _is_credits_exhausted_message(body: dict | None) -> bool:
    if not body:
        return False
    message = str(body.get("message", "")).lower()
    return "run out of api credits" in message or "api credits" in message and "limit" in message


async def throttled_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict,
    reason: str = "api",
) -> httpx.Response:
    global _last_request_at
    estimated = estimate_request_credits(params)
    if await should_skip_twelvedata_api(estimated):
        report = await get_credit_usage_report()
        logger.warning(
            "twelvedata_request_skipped_budget",
            reason=reason,
            estimated_credits=estimated,
            **report,
        )
        return httpx.Response(
            429,
            json={"status": "error", "message": "run out of api credits for the current day"},
            request=httpx.Request("GET", url),
        )

    min_gap = settings.twelvedata_min_gap_seconds
    async with _lock:
        now = time.monotonic()
        wait = min_gap - (now - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        response = await client.get(url, params=params)
        _last_request_at = time.monotonic()

        if response.status_code == 429:
            body: dict | None = None
            try:
                body = response.json()
            except Exception:
                pass
            await record_twelvedata_429(body)
            return response

        if response.is_success:
            actual = estimated
            try:
                payload = response.json()
                if isinstance(payload.get("values"), list) and payload["values"]:
                    actual = len(payload["values"])
            except Exception:
                pass
            await record_credits_used(actual, reason=reason)

        return response
