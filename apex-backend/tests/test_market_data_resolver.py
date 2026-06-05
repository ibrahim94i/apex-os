"""Tests for live market data resolver fallback chain."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.data_source_monitor import clear_failover_state, report_live_bar_source
from app.services.market_data_resolver import fetch_live_bar_with_fallback


@pytest.fixture(autouse=True)
def _reset_monitor() -> None:
    clear_failover_state()
    yield
    clear_failover_state()


@pytest.mark.asyncio
async def test_resolver_uses_twelvedata_when_available() -> None:
    td_bar = {
        "symbol": "EURUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 1.08,
        "high": 1.09,
        "low": 1.07,
        "close": 1.085,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }
    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=td_bar),
    ):
        bar, source = await fetch_live_bar_with_fallback("EURUSD", "EUR/USD")
    assert source == "twelvedata"
    assert bar == td_bar


@pytest.mark.asyncio
async def test_resolver_falls_back_to_finnhub() -> None:
    fh_bar = {
        "symbol": "EURUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 1.08,
        "high": 1.09,
        "low": 1.07,
        "close": 1.085,
        "volume": 0.0,
        "source": "finnhub",
        "is_closed": True,
    }
    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.services.market_data_resolver._fetch_finnhub_live",
            new=AsyncMock(return_value=fh_bar),
        ):
            with patch(
                "app.services.market_data_resolver.report_live_bar_source",
                new=AsyncMock(),
            ) as mock_report:
                bar, source = await fetch_live_bar_with_fallback("EURUSD", "EUR/USD")
    assert source == "finnhub"
    assert bar == fh_bar
    mock_report.assert_awaited_once_with("EURUSD", "finnhub")


@pytest.mark.asyncio
async def test_resolver_falls_back_to_db_without_telegram() -> None:
    db_bar = {
        "symbol": "GBPUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 1.27,
        "high": 1.28,
        "low": 1.26,
        "close": 1.275,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }
    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.services.market_data_resolver._fetch_finnhub_live",
            new=AsyncMock(return_value=None),
        ):
            with patch(
                "app.services.market_data_resolver._fetch_db_latest",
                new=AsyncMock(return_value=db_bar),
            ):
                with patch(
                    "app.services.market_data_resolver.report_live_bar_source",
                    new=AsyncMock(),
                ) as mock_report:
                    bar, source = await fetch_live_bar_with_fallback("GBPUSD", "GBP/USD")
    assert source == "db"
    assert bar == db_bar
    mock_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_finnhub_not_called_when_twelvedata_succeeds() -> None:
    td_bar = {
        "symbol": "EURUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 1.08,
        "high": 1.09,
        "low": 1.07,
        "close": 1.085,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }
    mock_fh = AsyncMock()
    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=td_bar),
    ):
        with patch(
            "app.services.market_data_resolver._fetch_finnhub_live",
            mock_fh,
        ):
            bar, source = await fetch_live_bar_with_fallback("EURUSD", "EUR/USD")
    assert source == "twelvedata"
    assert bar == td_bar
    mock_fh.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_return_to_twelvedata_after_finnhub() -> None:
    fh_bar = {
        "symbol": "EURUSD",
        "timestamp": "2026-06-01T11:00:00+00:00",
        "open": 1.08,
        "high": 1.09,
        "low": 1.07,
        "close": 1.085,
        "volume": 0.0,
        "source": "finnhub",
        "is_closed": True,
    }
    td_bar = {
        "symbol": "EURUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 1.09,
        "high": 1.10,
        "low": 1.08,
        "close": 1.095,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }

    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.services.market_data_resolver._fetch_finnhub_live",
            new=AsyncMock(return_value=fh_bar),
        ):
            with patch(
                "app.services.market_data_resolver.report_live_bar_source",
                new=AsyncMock(wraps=report_live_bar_source),
            ):
                bar, source = await fetch_live_bar_with_fallback("EURUSD", "EUR/USD")
    assert source == "finnhub"

    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=td_bar),
    ):
        with patch(
            "app.services.market_data_resolver.report_live_bar_source",
            new=AsyncMock(wraps=report_live_bar_source),
        ):
            bar, source = await fetch_live_bar_with_fallback("EURUSD", "EUR/USD")
    assert source == "twelvedata"
    assert bar == td_bar
