"""Tests for H1 bar close gating."""

import pytest

from app.services.h1_bar_gate import (
    mark_h1_pipeline_processed,
    normalize_h1_bucket,
    should_run_h1_pipeline,
)


@pytest.mark.asyncio
async def test_should_run_h1_pipeline_once_per_hour(monkeypatch) -> None:
    store: dict[str, dict] = {}

    async def fake_get(key: str):
        return store.get(key)

    async def fake_set(key: str, value: dict, ttl: int = 0):
        store[key] = value

    monkeypatch.setattr("app.services.h1_bar_gate.cache_get", fake_get)
    monkeypatch.setattr("app.services.h1_bar_gate.cache_set", fake_set)

    ts = "2026-06-10T14:37:00+00:00"
    assert normalize_h1_bucket(ts) == "2026-06-10T14:00:00+00:00"
    assert await should_run_h1_pipeline("XAUUSD", ts) is True
    await mark_h1_pipeline_processed("XAUUSD", ts)
    assert await should_run_h1_pipeline("XAUUSD", ts) is False
    assert await should_run_h1_pipeline("XAUUSD", "2026-06-10T15:05:00+00:00") is True
