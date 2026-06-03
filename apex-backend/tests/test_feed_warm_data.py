"""Tests for feed health warm-data detection."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.feed_health_service import check_feed_health


@pytest.mark.asyncio
async def test_feed_not_stale_when_bootstrap_data_present() -> None:
    with patch("app.services.feed_health_service.get_feed_last_update", new_callable=AsyncMock, return_value=None):
        with patch(
            "app.services.feed_health_service.get_latest_price",
            new_callable=AsyncMock,
            return_value={"price": 1.16, "timestamp": "2026-06-03T20:00:00+00:00"},
        ):
            with patch(
                "app.services.feed_health_service.get_latest_regime",
                new_callable=AsyncMock,
                return_value={"symbol": "EURUSD", "regime": "TRENDING_DOWN"},
            ):
                with patch("app.services.feed_health_service.is_market_open", return_value=True):
                    with patch("app.services.feed_health_service.feed_manager") as mock_mgr:
                        mock_mgr.is_running.return_value = True
                        status = await check_feed_health("EURUSD")

    assert status.stale is False
    assert status.symbol == "EURUSD"
