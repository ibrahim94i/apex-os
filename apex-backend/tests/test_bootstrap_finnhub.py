"""Bootstrap uses Alpha Vantage first, then DB."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.history_bootstrap import fetch_bootstrap_history


@pytest.mark.asyncio
async def test_bootstrap_history_prefers_alphavantage() -> None:
    asset = ASSETS["EURUSD"]
    av_bars = [{"symbol": "EURUSD", "timestamp": "2026-06-01T12:00:00+00:00", "close": 1.08}] * 250
    with patch(
        "app.feeds.alphavantage_client.fetch_fx_intraday_bars",
        new=AsyncMock(return_value=av_bars),
    ) as mock_av:
        bars = await fetch_bootstrap_history(asset, limit=250)
    assert len(bars) == 250
    mock_av.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_history_falls_back_to_db() -> None:
    asset = ASSETS["USDJPY"]
    db_bars = [{"symbol": "USDJPY", "timestamp": "2026-06-01T12:00:00+00:00", "close": 156.0}]
    with patch(
        "app.feeds.alphavantage_client.fetch_fx_intraday_bars",
        new=AsyncMock(return_value=[]),
    ):
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
