"""Tests for chart-only timeframe bars."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.chart_bars_service import (
    DEFAULT_CHART_TIMEFRAME,
    fetch_chart_bars,
    normalize_chart_timeframe,
)


def test_normalize_chart_timeframe() -> None:
    assert normalize_chart_timeframe("h1") == "H1"
    assert normalize_chart_timeframe("M5") == "M5"


def test_normalize_chart_timeframe_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        normalize_chart_timeframe("M30")


@pytest.mark.asyncio
async def test_fetch_chart_bars_h1_uses_db() -> None:
    sample = [{"symbol": "XAUUSD", "timestamp": "2026-06-01T00:00:00+00:00", "close": 1.0}]
    with patch(
        "app.services.chart_bars_service.fetch_bars_from_db",
        new_callable=AsyncMock,
        return_value=sample,
    ) as mock_db:
        bars, timeframe = await fetch_chart_bars("XAUUSD", interval="H1", limit=200)
    mock_db.assert_awaited_once_with("XAUUSD", 200)
    assert bars == sample
    assert timeframe == DEFAULT_CHART_TIMEFRAME


@pytest.mark.asyncio
async def test_fetch_chart_bars_m5_uses_twelvedata() -> None:
    sample = [{"symbol": "XAUUSD", "timestamp": "2026-06-01T00:05:00+00:00", "close": 1.0}]
    with patch(
        "app.services.chart_bars_service._fetch_twelvedata_chart_series",
        new_callable=AsyncMock,
        return_value=sample,
    ) as mock_td:
        bars, timeframe = await fetch_chart_bars("XAUUSD", interval="M5", limit=120)
    mock_td.assert_awaited_once()
    assert bars == sample
    assert timeframe == "M5"
