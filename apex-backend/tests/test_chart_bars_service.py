"""Tests for chart-only timeframe bars."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.chart_bars_service import (
    DEFAULT_CHART_TIMEFRAME,
    fetch_chart_bars,
    normalize_chart_timeframe,
    resample_h1_bars_for_chart,
)


def _h1_bar(hour: int, price: float = 100.0) -> dict:
    return {
        "symbol": "XAUUSD",
        "timestamp": f"2026-06-01T{hour:02d}:00:00+00:00",
        "open": price,
        "high": price + 1,
        "low": price - 1,
        "close": price + 0.5,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }


def test_normalize_chart_timeframe() -> None:
    assert normalize_chart_timeframe("h1") == "H1"
    assert normalize_chart_timeframe("M5") == "M5"


def test_normalize_chart_timeframe_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        normalize_chart_timeframe("M30")


def test_resample_m5_expands_h1_bars() -> None:
    h1 = [_h1_bar(10), _h1_bar(11)]
    resampled = resample_h1_bars_for_chart(h1, "M5")
    assert len(resampled) == 24
    assert resampled[0]["timestamp"] != resampled[1]["timestamp"]


def test_resample_h4_aggregates() -> None:
    h1 = [_h1_bar(h, 100 + h) for h in range(8)]
    resampled = resample_h1_bars_for_chart(h1, "H4")
    assert len(resampled) == 2


@pytest.mark.asyncio
async def test_fetch_chart_bars_h1_uses_db() -> None:
    sample = [_h1_bar(0)]
    with patch(
        "app.services.chart_bars_service.fetch_bars_from_db",
        new_callable=AsyncMock,
        return_value=sample,
    ) as mock_db:
        bars, timeframe, source = await fetch_chart_bars("XAUUSD", interval="H1", limit=200)
    mock_db.assert_awaited_once_with("XAUUSD", 500)
    assert bars == sample
    assert timeframe == DEFAULT_CHART_TIMEFRAME
    assert source == "db"


@pytest.mark.asyncio
async def test_fetch_chart_bars_m5_uses_binance() -> None:
    sample = [{"symbol": "XAUUSD", "timestamp": "2026-06-01T00:05:00+00:00", "close": 1.0}]
    with patch(
        "app.services.chart_bars_service.fetch_bars_from_db",
        new_callable=AsyncMock,
        return_value=[_h1_bar(0)],
    ):
        with patch(
            "app.services.chart_bars_service._fetch_binance_chart_series",
            new_callable=AsyncMock,
            return_value=sample,
        ) as mock_bn:
            bars, timeframe, source = await fetch_chart_bars("XAUUSD", interval="M5", limit=120)
    mock_bn.assert_awaited_once()
    assert bars == sample
    assert timeframe == "M5"
    assert source == "binance"


@pytest.mark.asyncio
async def test_fetch_chart_bars_m5_resamples_when_binance_unavailable() -> None:
    h1 = [_h1_bar(h) for h in range(4)]
    with patch(
        "app.services.chart_bars_service.fetch_bars_from_db",
        new_callable=AsyncMock,
        return_value=h1,
    ):
        with patch(
            "app.services.chart_bars_service._fetch_binance_chart_series",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with patch(
                "app.services.chart_bars_service._fetch_twelvedata_chart_series",
                new_callable=AsyncMock,
                return_value=[],
            ):
                bars, timeframe, source = await fetch_chart_bars("XAUUSD", interval="M5", limit=120)
    assert timeframe == "M5"
    assert source == "resampled"
    assert len(bars) == 48
