"""Tests for alert system and memory engine."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.alert_service import AlertService, AlertType
from app.services.memory_engine import memory_engine, time_of_day


def test_time_of_day_buckets() -> None:
    assert time_of_day(8) == "morning"
    assert time_of_day(14) == "afternoon"
    assert time_of_day(19) == "evening"
    assert time_of_day(2) == "night"


@pytest.mark.asyncio
async def test_high_confidence_signal_alert() -> None:
    service = AlertService()
    with patch.object(service, "_should_send", new_callable=AsyncMock, return_value=True):
        with patch.object(service, "_push", new_callable=AsyncMock) as mock_push:
            alert = await service.notify_new_signal("XAUUSD", "LONG", 0.82)
            assert alert.type == AlertType.HIGH_CONFIDENCE
            assert alert.fullscreen is True
            assert alert.play_sound == "critical"
            mock_push.assert_awaited_once()


@pytest.mark.asyncio
async def test_kill_switch_dedup() -> None:
    service = AlertService()
    with patch.object(service, "_should_send", new_callable=AsyncMock, return_value=False):
        with patch.object(service, "_push", new_callable=AsyncMock) as mock_push:
            result = await service.check_kill_switch(True, "test")
            assert result is None
            mock_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_consecutive_losses_yellow_overlay() -> None:
    service = AlertService()
    with patch.object(service, "_should_send", new_callable=AsyncMock, return_value=True):
        with patch.object(service, "_push", new_callable=AsyncMock):
            alert = await service.check_consecutive_losses(3)
            assert alert is not None
            assert alert.overlay_variant == "yellow"
            assert alert.play_sound == "warning"


@pytest.mark.asyncio
async def test_memory_get_top_patterns_db_fallback() -> None:
    with patch("app.services.memory_engine.cache_get", new_callable=AsyncMock, return_value=None):
        with patch.object(memory_engine, "_cache_top_patterns", new_callable=AsyncMock):
            with patch(
                "app.services.memory_engine.cache_get",
                new_callable=AsyncMock,
                side_effect=[None, [{"regime": "RANGING", "win_rate": 0.6}]],
            ):
                patterns = await memory_engine.get_top_patterns("BTCUSDT")
                assert len(patterns) == 1
