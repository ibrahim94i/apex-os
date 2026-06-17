"""Bootstrap Binance history for BTCUSDT."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.history_bootstrap import (
    BINANCE_BOOTSTRAP_BARS,
    bootstrap_asset,
    bootstrap_limit_for,
)


def test_btcusdt_bootstrap_limit_is_200() -> None:
    asset = ASSETS["BTCUSDT"]
    assert bootstrap_limit_for(asset) == BINANCE_BOOTSTRAP_BARS
    assert BINANCE_BOOTSTRAP_BARS == 200


@pytest.mark.asyncio
async def test_bootstrap_btcusdt_persists_200_bars() -> None:
    bars = [
        {
            "symbol": "BTCUSDT",
            "timestamp": f"2026-06-0{(i % 9) + 1}T{i % 24:02d}:00:00+00:00",
            "open": 60000.0 + i,
            "high": 60100.0 + i,
            "low": 59900.0 + i,
            "close": 60050.0 + i,
            "volume": 10.0,
            "source": "binance",
            "is_closed": True,
        }
        for i in range(200)
    ]
    mock_persist = AsyncMock(return_value=200)
    with patch(
        "app.feeds.history_bootstrap.fetch_bootstrap_history",
        new=AsyncMock(return_value=bars),
    ):
        with patch(
            "app.services.market_data_store.persist_bars_batch",
            mock_persist,
        ):
            with patch(
                "app.services.pipeline.process_bar",
                new=AsyncMock(),
            ):
                with patch(
                    "app.feeds.history_bootstrap._mark_feed_warmed",
                    new=AsyncMock(),
                ):
                    ok = await bootstrap_asset("BTCUSDT")
    assert ok is True
    mock_persist.assert_awaited_once()
    assert len(mock_persist.await_args.args[0]) == 200
