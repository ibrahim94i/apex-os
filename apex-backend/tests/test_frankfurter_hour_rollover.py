"""Frankfurter feed emits closed H1 bar on UTC hour rollover."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.feeds.frankfurter import FrankfurterFeed
from app.feeds.fx_rate_client import build_hourly_bar


@pytest.mark.asyncio
async def test_frankfurter_emits_closed_bar_on_hour_change() -> None:
    feed = FrankfurterFeed(from_symbol="USD", to_symbol="JPY", apex_symbol="USDJPY")
    on_bar = AsyncMock()
    feed.on_bar = on_bar
    feed._active_hour = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)
    feed._active_bar = build_hourly_bar(
        apex_symbol="USDJPY",
        price=150.0,
        at=feed._active_hour,
        source="exchangerate_api",
        is_closed=False,
    )
    feed._last_price = 149.8

    hour_eleven = datetime(2026, 6, 8, 11, 5, tzinfo=timezone.utc)
    with patch(
        "app.feeds.frankfurter.fetch_latest_rate_with_source",
        new=AsyncMock(return_value=(150.5, "exchangerate_api")),
    ):
        with patch("app.feeds.frankfurter.set_latest_price", new=AsyncMock()):
            with patch("app.feeds.frankfurter.set_feed_last_update", new=AsyncMock()):
                with patch("app.feeds.frankfurter.set_feed_status", new=AsyncMock()):
                    with patch("app.feeds.frankfurter.datetime") as mock_dt:
                        mock_dt.now.return_value = hour_eleven
                        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
                        assert await feed._poll_once() is True

    assert on_bar.await_count == 2
    closed_call = on_bar.await_args_list[0].args[0]
    open_call = on_bar.await_args_list[1].args[0]
    assert closed_call["is_closed"] is True
    assert closed_call["timestamp"].startswith("2026-06-08T10:00:00")
    assert open_call["is_closed"] is False
    assert open_call["timestamp"].startswith("2026-06-08T11:00:00")
