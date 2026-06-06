"""XAUUSD bootstrap — 500 H1 bars, runs even when market closed."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.history_bootstrap import (
    XAUUSD_BOOTSTRAP_BARS,
    bootstrap_asset,
    bootstrap_limit_for,
    bootstrap_success_threshold,
)


def test_xauusd_bootstrap_limit_is_500() -> None:
    asset = ASSETS["XAUUSD"]
    assert bootstrap_limit_for(asset) == 500
    assert XAUUSD_BOOTSTRAP_BARS == 500


def test_xauusd_success_threshold_requires_200() -> None:
    asset = ASSETS["XAUUSD"]
    assert bootstrap_success_threshold(asset, 500) == 200


@pytest.mark.asyncio
async def test_bootstrap_xauusd_runs_when_market_closed() -> None:
    bars = [
        {
            "symbol": "XAUUSD",
            "timestamp": f"2026-05-{(i % 28) + 1:02d}T{i % 24:02d}:00:00+00:00",
            "open": 4400.0 + i,
            "high": 4410.0 + i,
            "low": 4390.0 + i,
            "close": 4405.0 + i,
            "volume": 0.0,
            "source": "twelvedata",
            "is_closed": True,
        }
        for i in range(500)
    ]
    with patch(
        "app.feeds.history_bootstrap.fetch_bootstrap_history",
        new=AsyncMock(return_value=bars),
    ):
        with patch(
            "app.services.market_data_store.persist_bars_batch",
            new=AsyncMock(return_value=500),
        ):
            with patch("app.services.pipeline.seed_bars_to_buffer"):
                with patch("app.services.pipeline.process_bar", new=AsyncMock()):
                    with patch("app.feeds.history_bootstrap._mark_feed_warmed", new=AsyncMock()):
                        with patch("app.services.market_hours.is_market_open", return_value=False):
                            ok = await bootstrap_asset("XAUUSD")
    assert ok is True
