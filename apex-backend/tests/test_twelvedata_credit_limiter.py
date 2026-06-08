"""Tests for TwelveData daily credit budget tracking."""

from app.feeds.twelvedata_limiter import (
    can_afford_credits,
    clear_feed_recovery_pause,
    credits_remaining_today,
    estimate_request_credits,
    get_credit_usage_report,
    is_credits_exhausted,
    mark_credits_exhausted,
    record_credits_used,
    should_skip_twelvedata_api,
)


def setup_function() -> None:
    clear_feed_recovery_pause()


def test_estimate_request_credits_from_outputsize() -> None:
    assert estimate_request_credits({"outputsize": 500}) == 500
    assert estimate_request_credits({}) == 1


def test_record_credits_used_marks_exhausted_at_limit() -> None:
    assert is_credits_exhausted() is False
    record_credits_used(799, reason="test")
    assert credits_remaining_today() == 1
    record_credits_used(1, reason="test")
    assert is_credits_exhausted() is True
    assert should_skip_twelvedata_api(1) is True


def test_can_afford_blocks_large_bootstrap() -> None:
    record_credits_used(400, reason="bootstrap")
    assert can_afford_credits(500) is False
    assert can_afford_credits(1) is True


def test_mark_credits_exhausted_blocks_requests() -> None:
    mark_credits_exhausted()
    report = get_credit_usage_report()
    assert report["exhausted"] is True
    assert should_skip_twelvedata_api(1) is True
