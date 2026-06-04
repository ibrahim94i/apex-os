"""Tests for stale feed auto-recovery."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.feed_health_service import recover_feed


@pytest.mark.asyncio
async def test_recover_feed_bootstraps_when_regime_exists_but_data_stale() -> None:
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()

    with patch("app.services.feed_health_service.feed_manager") as mock_mgr:
        mock_feed = AsyncMock()
        mock_feed.fetch_now = AsyncMock(return_value=False)
        mock_mgr.restart_feed = AsyncMock(return_value=True)
        mock_mgr.get_feed.return_value = mock_feed
        with patch("app.services.feed_health_service.set_feed_status", new_callable=AsyncMock):
            with patch(
                "app.services.feed_health_service.get_feed_last_update",
                new_callable=AsyncMock,
                return_value={"timestamp": stale_ts},
            ):
                with patch(
                    "app.services.feed_health_service.get_latest_price",
                    new_callable=AsyncMock,
                    return_value={"price": 1.08, "timestamp": stale_ts},
                ):
                    with patch(
                        "app.feeds.history_bootstrap.bootstrap_asset",
                        new_callable=AsyncMock,
                        return_value=True,
                    ) as mock_bootstrap:
                        ok = await recover_feed("EURUSD", "data_stale")
    assert ok is True
    mock_bootstrap.assert_awaited_once_with("EURUSD")


@pytest.mark.asyncio
async def test_recover_feed_skips_bootstrap_when_data_fresh() -> None:
    fresh_ts = datetime.now(timezone.utc).isoformat()

    with patch("app.services.feed_health_service.feed_manager") as mock_mgr:
        mock_feed = AsyncMock()
        mock_feed.fetch_now = AsyncMock(return_value=True)
        mock_mgr.restart_feed = AsyncMock(return_value=True)
        mock_mgr.get_feed.return_value = mock_feed
        with patch("app.services.feed_health_service.set_feed_status", new_callable=AsyncMock):
            with patch(
                "app.services.feed_health_service.get_feed_last_update",
                new_callable=AsyncMock,
                return_value={"timestamp": fresh_ts},
            ):
                with patch(
                    "app.feeds.history_bootstrap.bootstrap_asset",
                    new_callable=AsyncMock,
                ) as mock_bootstrap:
                    ok = await recover_feed("XAUUSD", "test")
    assert ok is True
    mock_bootstrap.assert_not_awaited()
