"""Tests for feed manager and health recovery."""

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

    with patch("app.services.feed_health_service.feed_manager") as mock_mgr:
        mock_mgr.restart_feed = AsyncMock(return_value=True)
        mock_mgr.get_feed.return_value = None
        with patch(
            "app.feeds.history_bootstrap.bootstrap_asset",
            new_callable=AsyncMock,
            return_value=True,
        ):
            ok = await recover_feed("EURUSD", "test")
            assert ok is True
            mock_mgr.restart_feed.assert_awaited_once_with("EURUSD")
