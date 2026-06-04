"""Finnhub economic calendar — high-impact events for trading blackout windows."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.logging_config import logger
from app.schemas.agent import EconomicEventSchema

FINNHUB_CALENDAR_URL = "https://finnhub.io/api/v1/calendar/economic"

_CACHE: tuple[float, list[EconomicEventSchema]] | None = None
_CACHE_TTL_SECONDS: float = 300.0  # overridden from settings on first fetch


def _is_configured() -> bool:
    key = settings.finnhub_api_key
    return bool(key and key != "your_key_here")


def parse_event_time(raw: str) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text[:19] if " " in fmt else text[:10], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def minutes_until_event(event_time: datetime, at: datetime | None = None) -> float:
    """Minutes from `at` until event (negative = event already passed)."""
    ref = at or datetime.now(timezone.utc)
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    return (event_time - ref).total_seconds() / 60.0


def _normalize_impact(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _row_to_event(row: dict[str, Any]) -> EconomicEventSchema | None:
    impact = _normalize_impact(row.get("impact"))
    if impact != "high":
        return None
    event_time = parse_event_time(str(row.get("time") or ""))
    if event_time is None:
        return None
    name = str(row.get("event") or "").strip()
    if not name:
        return None
    return EconomicEventSchema(
        event=name,
        country=str(row.get("country") or "").strip(),
        impact=impact,
        event_time=event_time,
        estimate=_optional_float(row.get("estimate")),
        previous=_optional_float(row.get("prev") or row.get("previous")),
        actual=_optional_float(row.get("actual")),
        unit=str(row.get("unit") or "").strip(),
    )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _fetch_calendar_rows(from_date: str, to_date: str) -> list[dict[str, Any]]:
    if not _is_configured():
        return []

    params = {
        "from": from_date,
        "to": to_date,
        "token": settings.finnhub_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(FINNHUB_CALENDAR_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("finnhub_calendar_fetch_failed", error=str(exc))
        return []

    if not isinstance(data, dict):
        return []
    rows = data.get("economicCalendar")
    return rows if isinstance(rows, list) else []


async def _load_high_impact_events(
    *,
    lookback_minutes: int = 20,
    hours_ahead: int = 24,
) -> list[EconomicEventSchema]:
    global _CACHE
    ttl = float(settings.finnhub_calendar_cache_ttl_seconds)
    now = time.monotonic()
    if _CACHE and (now - _CACHE[0]) < ttl:
        return _CACHE[1]

    ref = datetime.now(timezone.utc)
    from_dt = (ref - timedelta(minutes=lookback_minutes)).strftime("%Y-%m-%d")
    to_dt = (ref + timedelta(hours=hours_ahead + 1)).strftime("%Y-%m-%d")

    events: list[EconomicEventSchema] = []
    for row in await _fetch_calendar_rows(from_dt, to_dt):
        if not isinstance(row, dict):
            continue
        parsed = _row_to_event(row)
        if parsed:
            events.append(parsed)

    events.sort(key=lambda e: e.event_time)
    _CACHE = (now, events)
    logger.info("finnhub_calendar_loaded", high_impact=len(events))
    return events


async def fetch_upcoming_high_impact_events(
    *,
    hours_ahead: int = 24,
    reference_time: datetime | None = None,
) -> list[EconomicEventSchema]:
    """High-impact Finnhub events in the next `hours_ahead` hours (UTC)."""
    ref = reference_time or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    end = ref + timedelta(hours=hours_ahead)
    all_events = await _load_high_impact_events(hours_ahead=hours_ahead)
    return [e for e in all_events if ref <= e.event_time <= end]


def find_event_in_blackout_window(
    events: list[EconomicEventSchema],
    at: datetime | None = None,
    *,
    pre_minutes: int | None = None,
    post_minutes: int | None = None,
) -> EconomicEventSchema | None:
    """Return first high-impact event in [T-pre, T+post] blackout window."""
    ref = at or datetime.now(timezone.utc)
    pre = pre_minutes if pre_minutes is not None else settings.economic_calendar_pre_event_minutes
    post = post_minutes if post_minutes is not None else settings.economic_calendar_post_event_minutes
    for event in events:
        mins = minutes_until_event(event.event_time, ref)
        if -post <= mins <= pre:
            return event
    return None


def find_imminent_event(
    events: list[EconomicEventSchema],
    at: datetime | None = None,
    *,
    within_minutes: int | None = None,
) -> EconomicEventSchema | None:
    """Next upcoming event within N minutes (not yet started)."""
    ref = at or datetime.now(timezone.utc)
    window = within_minutes if within_minutes is not None else settings.economic_calendar_news_warn_minutes
    imminent: EconomicEventSchema | None = None
    best_mins = float("inf")
    for event in events:
        mins = minutes_until_event(event.event_time, ref)
        if 0 <= mins <= window and mins < best_mins:
            imminent = event
            best_mins = mins
    return imminent
