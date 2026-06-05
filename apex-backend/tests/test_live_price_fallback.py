"""Tests for live price fallback chain."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.live_price_fallback import fetch_live_fallback_bar


@pytest.mark.asyncio
async def test_live_fallback_uses_frankfurter_first() -> None:
    asset = ASSETS["EURUSD"]
    bar = {"symbol": "EURUSD", "close": 1.08, "source": "frankfurter"}
    with patch(
        "app.feeds.live_price_fallback.fetch_frankfurter_live_bar",
        new=AsyncMock(return_value=bar),
    ) as mock_ff:
        result, source = await fetch_live_fallback_bar(asset)
    assert source == "frankfurter"
    assert result == bar
    mock_ff.assert_awaited_once()


@pytest.mark.asyncio
async def test_live_fallback_skips_to_alphavantage_when_frankfurter_fails() -> None:
    asset = ASSETS["GBPUSD"]
    av_bar = {"symbol": "GBPUSD", "close": 1.27, "source": "alphavantage"}
    with patch(
        "app.feeds.live_price_fallback.fetch_frankfurter_live_bar",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.feeds.live_price_fallback.fetch_alphavantage_live_bar",
            new=AsyncMock(return_value=av_bar),
        ):
            result, source = await fetch_live_fallback_bar(asset)
    assert source == "alphavantage"
    assert result == av_bar
