"""Shared time helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_utc_timestamp(raw: str | datetime) -> datetime:
    if isinstance(raw, datetime):
        ts = raw
    else:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def compute_age_seconds(
    reference: datetime | str,
    now: datetime | None = None,
) -> int:
    """Seconds since reference time; never negative (future bar / clock skew → 0)."""
    ref = parse_utc_timestamp(reference)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return max(0, int((current - ref).total_seconds()))
