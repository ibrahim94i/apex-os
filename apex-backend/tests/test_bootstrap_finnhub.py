"""Bootstrap uses Finnhub first, then DB."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.history_bootstrap import fetch_bootstrap_history


@pytest.mark.asyncio
async def test_bootstrap_history_prefers_finnhub() -> None:
    asset = ASSETS["EURUSD"]
    finnhub_bars = [{"symbol": "EURUSD", "timestamp": "2026-06-01T12:00:00+00:00", "close": 1.08}]
    with patch(
        "app.feeds.finnhub_market.fetch_finnhub_history",
        new=AsyncMock(return_value=finnhub_bars),
    ) as mock_fh:
        bars = await fetch_bootstrap_history(asset, limit=250)
    assert bars == finnhub_bars
    mock_fh.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_history_falls_back_to_db() -> None:
    asset = ASSETS["USDJPY"]
    db_bars = [{"symbol": "USDJPY", "timestamp": "2026-06-01T12:00:00+00:00", "close": 156.0}]
    with patch(
        "app.feeds.finnhub_market.fetch_finnhub_history",
        new=AsyncMock(return_value=[]),
    ):
        with patch(
            "app.services.market_data_store.fetch_bars_from_db",
            new=AsyncMock(return_value=db_bars),
        ):
            bars = await fetch_bootstrap_history(asset, limit=250)
    assert bars == db_bars
