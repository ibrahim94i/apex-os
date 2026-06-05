"""Bootstrap uses feed-type primary source, then DB."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.history_bootstrap import fetch_bootstrap_history


@pytest.mark.asyncio
async def test_bootstrap_gold_uses_twelvedata() -> None:
    asset = ASSETS["XAUUSD"]
    td_bars = [{"symbol": "XAUUSD", "timestamp": "2026-06-01T12:00:00+00:00", "close": 4400.0}] * 250
    with patch(
        "app.feeds.history_bootstrap.fetch_twelvedata_history",
        new=AsyncMock(return_value=td_bars),
    ) as mock_td:
        bars = await fetch_bootstrap_history(asset, limit=250)
    assert len(bars) == 250
    mock_td.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_fx_uses_frankfurter() -> None:
    asset = ASSETS["EURUSD"]
    ff_bars = [{"symbol": "EURUSD", "timestamp": "2026-06-01T12:00:00+00:00", "close": 1.08}] * 250
    with patch(
        "app.feeds.history_bootstrap.fetch_frankfurter_history",
        new=AsyncMock(return_value=ff_bars),
    ) as mock_ff:
        bars = await fetch_bootstrap_history(asset, limit=250)
    assert len(bars) == 250
    mock_ff.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_history_falls_back_to_db() -> None:
    asset = ASSETS["USDJPY"]
    db_bars = [{"symbol": "USDJPY", "timestamp": "2026-06-01T12:00:00+00:00", "close": 156.0}]
    with patch(
        "app.feeds.history_bootstrap.fetch_frankfurter_history",
        new=AsyncMock(return_value=[]),
    ):
        with patch(
            "app.services.market_data_store.fetch_bars_from_db",
            new=AsyncMock(return_value=db_bars),
        ):
            bars = await fetch_bootstrap_history(asset, limit=250)
    assert bars == db_bars
