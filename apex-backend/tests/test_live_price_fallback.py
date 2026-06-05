"""Tests for legacy live_price_fallback helpers (Frankfurter spot bars)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.live_price_fallback import fetch_live_fallback_bar


@pytest.mark.asyncio
async def test_live_fallback_uses_exchangerate_api_for_fx() -> None:
    asset = ASSETS["EURUSD"]
    bar = {"symbol": "EURUSD", "close": 1.08, "source": "exchangerate_api"}
    with patch(
        "app.feeds.live_price_fallback.fetch_latest_rate_with_source",
        new=AsyncMock(return_value=(1.08, "exchangerate_api")),
    ) as mock_ff:
        with patch(
            "app.feeds.live_price_fallback.build_hourly_bar",
            return_value=bar,
        ):
            result, source = await fetch_live_fallback_bar(asset)
    assert source == "exchangerate_api"
    assert result == bar
    mock_ff.assert_awaited_once()


@pytest.mark.asyncio
async def test_live_fallback_returns_none_when_all_fail() -> None:
    asset = ASSETS["GBPUSD"]
    with patch(
        "app.feeds.live_price_fallback.fetch_latest_rate_with_source",
        new=AsyncMock(return_value=(None, None)),
    ):
        with patch(
            "app.feeds.live_price_fallback.fetch_finnhub_live_bar",
            new=AsyncMock(return_value=None),
        ):
            result, source = await fetch_live_fallback_bar(asset)
    assert source is None
    assert result is None
