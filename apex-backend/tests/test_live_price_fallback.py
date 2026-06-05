"""Tests for legacy live_price_fallback helpers (Frankfurter spot bars)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config.assets import ASSETS
from app.feeds.live_price_fallback import fetch_live_fallback_bar


@pytest.mark.asyncio
async def test_live_fallback_uses_frankfurter_for_fx() -> None:
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
async def test_live_fallback_returns_none_when_all_fail() -> None:
    asset = ASSETS["GBPUSD"]
    with patch(
        "app.feeds.live_price_fallback.fetch_frankfurter_live_bar",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.feeds.live_price_fallback.fetch_finnhub_live_bar",
            new=AsyncMock(return_value=None),
        ):
            result, source = await fetch_live_fallback_bar(asset)
    assert source is None
    assert result is None
