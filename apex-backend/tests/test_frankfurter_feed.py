"""Frankfurter feed DB fallback when API fails."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.feeds.frankfurter import FrankfurterFeed


@pytest.mark.asyncio
async def test_frankfurter_falls_back_to_db() -> None:
    feed = FrankfurterFeed(from_symbol="EUR", to_symbol="USD", apex_symbol="EURUSD")
    db_bar = {
        "symbol": "EURUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 1.08,
        "high": 1.09,
        "low": 1.07,
        "close": 1.085,
        "volume": 0.0,
        "source": "frankfurter",
        "is_closed": True,
    }
    on_bar = AsyncMock()
    feed.on_bar = on_bar

    with patch(
        "app.feeds.frankfurter.fetch_latest_rate_with_source",
        new=AsyncMock(return_value=(None, None)),
    ):
        with patch(
            "app.feeds.frankfurter.fetch_bars_from_db",
            new=AsyncMock(return_value=[db_bar]),
        ):
            with patch("app.feeds.frankfurter.set_latest_price", new=AsyncMock()):
                with patch("app.feeds.frankfurter.set_feed_last_update", new=AsyncMock()):
                    with patch("app.feeds.frankfurter.set_feed_status", new=AsyncMock()):
                        ok = await feed._poll_once()

    assert ok is True
    on_bar.assert_awaited_once()
    published = on_bar.await_args[0][0]
    assert published["source"] == "db"
