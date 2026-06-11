"""Tests for admin TwelveData credits reset endpoint."""

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.feeds import twelvedata_limiter
from app.feeds.twelvedata_limiter import (
    _CreditState,
    _credits_redis_key,
    _utc_day,
    clear_feed_recovery_pause,
    mark_credits_exhausted,
    record_twelvedata_429,
    reset_twelvedata_credits,
)
from app.main import app

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


@pytest.mark.asyncio
async def test_reset_twelvedata_credits_clears_exhausted_and_recovery_pause() -> None:
    await mark_credits_exhausted()
    await record_twelvedata_429()

    report = await reset_twelvedata_credits()

    assert report["exhausted"] is False
    assert report["used"] == 0
    assert report["recovery_paused"] is False
    assert _redis_store[_credits_redis_key()] == {"used": 0, "exhausted": False}


def test_admin_reset_endpoint_requires_key() -> None:
    with patch.object(settings, "admin_api_key", "secret-admin-key"):
        client = TestClient(app)
        response = client.post("/api/v1/admin/reset-twelvedata-credits")
        assert response.status_code == 403


def test_admin_reset_endpoint_resets_credits() -> None:
    with patch.object(settings, "admin_api_key", "secret-admin-key"):
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/reset-twelvedata-credits",
            headers={"X-Admin-Key": "secret-admin-key"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["redis_key"] == f"twelvedata_credits:{_utc_day()}"
        assert payload["credits"]["exhausted"] is False
        assert payload["credits"]["recovery_paused"] is False
