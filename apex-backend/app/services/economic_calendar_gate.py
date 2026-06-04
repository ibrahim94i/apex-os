"""Block automatic signals around high-impact economic releases."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.agent import EconomicEventSchema
from app.services.finnhub_calendar import find_event_in_blackout_window, minutes_until_event


def check_economic_calendar_gate(
    events: list[EconomicEventSchema],
    at: datetime | None = None,
) -> tuple[bool, str | None]:
    """
    Return (allowed, rejection_reason).
    Blocks when a high-impact event is within pre/post blackout window.
    `events` should include recent past releases (see finnhub_calendar._load_high_impact_events).
    """
    if not events:
        return True, None

    ref = at or datetime.now(timezone.utc)
    blocking = find_event_in_blackout_window(events, ref)
    if blocking is None:
        return True, None

    if minutes_until_event(blocking.event_time, ref) >= 0:
        return False, "economic_calendar_pre_event"
    return False, "economic_calendar_post_event"
