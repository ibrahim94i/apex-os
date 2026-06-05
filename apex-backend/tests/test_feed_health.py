"""Tests for feed manager and health recovery."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.feeds.manager import FeedManager


@pytest.mark.asyncio
async def test_feed_manager_tracks_symbols() -> None:
    mgr = FeedManager()
    mock_feed = MagicMock()
    mock_feed.is_running = False
    mock_feed.start = MagicMock()
    with patch.object(mgr, "_create_feed", return_value=mock_feed):
        assert mgr.start_feed("XAUUSD") is True
        mock_feed.start.assert_called_once()
        assert "XAUUSD" in mgr.get_status()


@pytest.mark.asyncio
async def test_recover_feed_restarts_and_bootstraps() -> None:
    from app.services.feed_health_service import recover_feed

    fresh_ts = datetime.now(timezone.utc).isoformat()

    with patch("app.services.feed_health_service.feed_manager") as mock_mgr:
        mock_mgr.restart_feed = AsyncMock(return_value=True)
        mock_mgr.get_feed.return_value = None
        with patch("app.services.feed_health_service.set_feed_status", new_callable=AsyncMock):
            with patch(
                "app.services.feed_health_service._is_feed_data_fresh",
                new_callable=AsyncMock,
                side_effect=[False, True],
            ):
                with patch(
                    "app.services.feed_health_service._feed_data_age_seconds",
                    new_callable=AsyncMock,
                    return_value=36_000,
                ):
                    with patch(
                        "app.services.feed_health_service.get_feed_last_update",
                        new_callable=AsyncMock,
                        return_value={"timestamp": fresh_ts, "received_at": fresh_ts},
                    ):
                        with patch(
                            "app.feeds.history_bootstrap.bootstrap_asset",
                            new_callable=AsyncMock,
                            return_value=True,
                        ) as mock_bootstrap:
                            with patch(
                                "app.core.cache.get_agent_consensus",
                                new_callable=AsyncMock,
                                return_value={"symbol": "EURUSD"},
                            ):
                                ok = await recover_feed("EURUSD", "test")
            assert ok is True
            mock_bootstrap.assert_awaited_once_with("EURUSD")
            mock_mgr.restart_feed.assert_awaited_once_with("EURUSD")
