"""Tests for live market data resolver fallback chain (gold only)."""

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
        "symbol": "XAUUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 4400.0,
        "high": 4410.0,
        "low": 4390.0,
        "close": 4405.0,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }
    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=td_bar),
    ):
        bar, source = await fetch_live_bar_with_fallback("XAUUSD", "XAU/USD")
    assert source == "twelvedata"
    assert bar == td_bar


@pytest.mark.asyncio
async def test_resolver_falls_back_to_db_without_telegram() -> None:
    db_bar = {
        "symbol": "XAUUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 4400.0,
        "high": 4410.0,
        "low": 4390.0,
        "close": 4405.0,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }
    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
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
                bar, source = await fetch_live_bar_with_fallback("XAUUSD", "XAU/USD")
    assert source == "db"
    assert bar == db_bar
    mock_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_db_not_called_when_twelvedata_succeeds() -> None:
    td_bar = {
        "symbol": "XAUUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 4400.0,
        "high": 4410.0,
        "low": 4390.0,
        "close": 4405.0,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }
    mock_db = AsyncMock()
    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=td_bar),
    ):
        with patch(
            "app.services.market_data_resolver._fetch_db_latest",
            mock_db,
        ):
            bar, source = await fetch_live_bar_with_fallback("XAUUSD", "XAU/USD")
    assert source == "twelvedata"
    assert bar == td_bar
    mock_db.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_return_to_twelvedata_after_db() -> None:
    db_bar = {
        "symbol": "XAUUSD",
        "timestamp": "2026-06-01T11:00:00+00:00",
        "open": 4390.0,
        "high": 4400.0,
        "low": 4380.0,
        "close": 4395.0,
        "volume": 0.0,
        "source": "db",
        "is_closed": True,
    }
    td_bar = {
        "symbol": "XAUUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 4400.0,
        "high": 4410.0,
        "low": 4390.0,
        "close": 4405.0,
        "volume": 0.0,
        "source": "twelvedata",
        "is_closed": True,
    }

    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.services.market_data_resolver._fetch_db_latest",
            new=AsyncMock(return_value=db_bar),
        ):
            bar, source = await fetch_live_bar_with_fallback("XAUUSD", "XAU/USD")
    assert source == "db"

    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=td_bar),
    ):
        with patch(
            "app.services.market_data_resolver.report_live_bar_source",
            new=AsyncMock(wraps=report_live_bar_source),
        ):
            bar, source = await fetch_live_bar_with_fallback("XAUUSD", "XAU/USD")
    assert source == "twelvedata"
    assert bar == td_bar
