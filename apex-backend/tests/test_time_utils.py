"""Tests for age_seconds calculation with future timestamps."""

from datetime import datetime, timedelta, timezone

from app.utils.time_utils import compute_age_seconds


def test_age_seconds_past_timestamp() -> None:
    ref = datetime.now(timezone.utc) - timedelta(minutes=5)
    age = compute_age_seconds(ref)
    assert 290 <= age <= 310


def test_age_seconds_future_timestamp_clamped_to_zero() -> None:
    ref = datetime.now(timezone.utc) + timedelta(hours=9)
    assert compute_age_seconds(ref) == 0


def test_age_seconds_iso_string() -> None:
    ref = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    assert 115 <= compute_age_seconds(ref) <= 125
