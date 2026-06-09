"""Tests for TwelveData daily credit budget tracking."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.feeds import twelvedata_limiter
from app.feeds.twelvedata_limiter import (
    _CreditState,
    _credits_redis_key,
    _utc_day,
    can_afford_credits,
    clear_credit_tracking,
    clear_feed_recovery_pause,
    credits_remaining_today,
    estimate_request_credits,
    get_credit_usage_report,
    is_credits_exhausted,
    mark_credits_exhausted,
    record_credits_used,
    should_skip_twelvedata_api,
)

_redis_store: dict[str, Any] = {}


@pytest.fixture(autouse=True)
def _mock_redis_credits() -> Any:
    async def fake_get(key: str) -> Any | None:
        return _redis_store.get(key)

    async def fake_set(key: str, value: Any, ttl: int | None = None) -> None:
        _redis_store[key] = value

    async def fake_delete(key: str) -> None:
        _redis_store.pop(key, None)

    _redis_store.clear()
    clear_feed_recovery_pause()
    twelvedata_limiter._credit_state = _CreditState()

    with patch("app.feeds.twelvedata_limiter.cache_get", new=fake_get):
        with patch("app.feeds.twelvedata_limiter.cache_set", new=fake_set):
            with patch("app.feeds.twelvedata_limiter.cache_delete", new=fake_delete):
                yield

    _redis_store.clear()
    clear_feed_recovery_pause()
    twelvedata_limiter._credit_state = _CreditState()


def test_estimate_request_credits_from_outputsize() -> None:
    assert estimate_request_credits({"outputsize": 500}) == 500
    assert estimate_request_credits({}) == 1


@pytest.mark.asyncio
async def test_record_credits_used_marks_exhausted_at_limit() -> None:
    assert await is_credits_exhausted() is False
    await record_credits_used(799, reason="test")
    assert await credits_remaining_today() == 1
    await record_credits_used(1, reason="test")
    assert await is_credits_exhausted() is True
    assert await should_skip_twelvedata_api(1) is True


@pytest.mark.asyncio
async def test_can_afford_blocks_large_bootstrap() -> None:
    await record_credits_used(400, reason="bootstrap")
    assert await can_afford_credits(500) is False
    assert await can_afford_credits(1) is True


@pytest.mark.asyncio
async def test_mark_credits_exhausted_blocks_requests() -> None:
    await mark_credits_exhausted()
    report = await get_credit_usage_report()
    assert report["exhausted"] is True
    assert await should_skip_twelvedata_api(1) is True


@pytest.mark.asyncio
async def test_credit_state_persists_in_redis_across_reload() -> None:
    await record_credits_used(120, reason="bootstrap")
    twelvedata_limiter._credit_state = _CreditState()

    report = await get_credit_usage_report()
    assert report["used"] == 120
    assert report["exhausted"] is False


@pytest.mark.asyncio
async def test_exhausted_flag_persists_in_redis() -> None:
    await mark_credits_exhausted()
    twelvedata_limiter._credit_state = _CreditState()

    assert await should_skip_twelvedata_api(1) is True
    report = await get_credit_usage_report()
    assert report["exhausted"] is True


@pytest.mark.asyncio
async def test_credits_redis_key_uses_utc_day() -> None:
    assert _credits_redis_key() == f"twelvedata_credits:{_utc_day()}"


@pytest.mark.asyncio
async def test_clear_credit_tracking_resets_redis_and_memory() -> None:
    await record_credits_used(50, reason="test")
    await clear_credit_tracking()
    report = await get_credit_usage_report()
    assert report["used"] == 0
    assert report["exhausted"] is False
