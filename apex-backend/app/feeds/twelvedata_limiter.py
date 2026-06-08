"""Global rate limiter and daily credit budget for TwelveData API."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.logging_config import logger

_lock = asyncio.Lock()
_last_request_at: float = 0.0
_recovery_paused_until: datetime | None = None
_credits_used_today: int = 0
_credits_day: str = ""
_credits_exhausted: bool = False


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _reset_daily_counter_if_needed() -> None:
    global _credits_used_today, _credits_day, _credits_exhausted
    today = _utc_day()
    if _credits_day != today:
        _credits_day = today
        _credits_used_today = 0
        _credits_exhausted = False


def record_twelvedata_429(response_body: dict | None = None) -> None:
    """Pause feed recovery after TwelveData rate-limits us."""
    global _recovery_paused_until
    pause = settings.twelvedata_429_recovery_pause_seconds
    _recovery_paused_until = datetime.now(timezone.utc) + timedelta(seconds=pause)
    if _is_credits_exhausted_message(response_body):
        mark_credits_exhausted()


def mark_credits_exhausted() -> None:
    global _credits_exhausted
    _reset_daily_counter_if_needed()
    _credits_exhausted = True
    logger.warning(
        "twelvedata_credits_exhausted",
        used=_credits_used_today,
        limit=settings.twelvedata_daily_credit_limit,
        day=_credits_day,
    )


def record_credits_used(credits: int, *, reason: str) -> None:
    """Track estimated TwelveData credits consumed (1 credit per data point)."""
    global _credits_used_today
    if credits <= 0:
        return
    _reset_daily_counter_if_needed()
    _credits_used_today += credits
    limit = settings.twelvedata_daily_credit_limit
    logger.info(
        "twelvedata_credits_used",
        credits=credits,
        used_today=_credits_used_today,
        limit=limit,
        remaining=max(limit - _credits_used_today, 0),
        reason=reason,
    )
    if _credits_used_today >= limit:
        mark_credits_exhausted()


def estimate_request_credits(params: dict) -> int:
    raw = params.get("outputsize", 1)
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1


def credits_remaining_today() -> int:
    _reset_daily_counter_if_needed()
    return max(settings.twelvedata_daily_credit_limit - _credits_used_today, 0)


def is_credits_exhausted() -> bool:
    _reset_daily_counter_if_needed()
    if _credits_exhausted:
        return True
    return _credits_used_today >= settings.twelvedata_daily_credit_limit


def can_afford_credits(credits: int) -> bool:
    _reset_daily_counter_if_needed()
    if _credits_exhausted:
        return False
    return _credits_used_today + credits <= settings.twelvedata_daily_credit_limit


def should_skip_twelvedata_api(credits: int = 1) -> bool:
    """Skip API when credits are gone or a recent 429 pause is active."""
    if is_credits_exhausted():
        return True
    if not can_afford_credits(credits):
        return True
    return False


def get_credit_usage_report() -> dict[str, int | str | bool]:
    _reset_daily_counter_if_needed()
    limit = settings.twelvedata_daily_credit_limit
    return {
        "day": _credits_day,
        "used": _credits_used_today,
        "limit": limit,
        "remaining": max(limit - _credits_used_today, 0),
        "exhausted": is_credits_exhausted(),
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
    """Test helper — reset 429 recovery pause and credit counters."""
    global _recovery_paused_until, _credits_used_today, _credits_day, _credits_exhausted
    _recovery_paused_until = None
    _credits_used_today = 0
    _credits_day = ""
    _credits_exhausted = False


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
    if should_skip_twelvedata_api(estimated):
        logger.warning(
            "twelvedata_request_skipped_budget",
            reason=reason,
            estimated_credits=estimated,
            **get_credit_usage_report(),
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
            record_twelvedata_429(body)
            return response

        if response.is_success:
            actual = estimated
            try:
                payload = response.json()
                if isinstance(payload.get("values"), list) and payload["values"]:
                    actual = len(payload["values"])
            except Exception:
                pass
            record_credits_used(actual, reason=reason)

        return response
