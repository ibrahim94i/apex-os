"""Tests for live market data resolver fallback chain."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.data_source_monitor import clear_failover_state
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
        "symbol": "XAUUSD",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "open": 3300.0,
        "high": 3310.0,
        "low": 3295.0,
        "close": 3305.0,
        "volume": 0.0,
        "source": "finnhub",
        "is_closed": True,
    }
    with patch(
        "app.services.market_data_resolver._fetch_twelvedata_latest",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.services.market_data_resolver.fetch_finnhub_latest_bar",
            new=AsyncMock(return_value=fh_bar),
        ):
            with patch(
                "app.services.market_data_resolver.report_live_bar_source",
                new=AsyncMock(),
            ):
                bar, source = await fetch_live_bar_with_fallback("XAUUSD", "XAU/USD")
    assert source == "finnhub"
    assert bar == fh_bar


@pytest.mark.asyncio
async def test_resolver_falls_back_to_db() -> None:
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
            "app.services.market_data_resolver.fetch_finnhub_latest_bar",
            new=AsyncMock(return_value=None),
        ):
            with patch(
                "app.services.market_data_resolver._fetch_db_latest",
                new=AsyncMock(return_value=db_bar),
            ):
                with patch(
                    "app.services.market_data_resolver.report_live_bar_source",
                    new=AsyncMock(),
                ):
                    bar, source = await fetch_live_bar_with_fallback("GBPUSD", "GBP/USD")
    assert source == "db"
    assert bar == db_bar


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
            "app.services.market_data_resolver.fetch_finnhub_latest_bar",
            mock_fh,
        ):
            with patch(
                "app.services.market_data_resolver.report_live_bar_source",
                new=AsyncMock(),
            ):
                bar, source = await fetch_live_bar_with_fallback("EURUSD", "EUR/USD")
    assert source == "twelvedata"
    assert bar == td_bar
    mock_fh.assert_not_awaited()


@pytest.mark.asyncio
async def test_twelvedata_tried_every_poll_even_during_recovery_pause() -> None:
    with patch("app.feeds.twelvedata_limiter.is_feed_recovery_paused", return_value=True):
        mock_td = AsyncMock(return_value=None)
        with patch(
            "app.services.market_data_resolver._fetch_twelvedata_latest",
            mock_td,
        ):
            with patch(
                "app.services.market_data_resolver.fetch_finnhub_latest_bar",
                new=AsyncMock(return_value=None),
            ):
                with patch(
                    "app.services.market_data_resolver._fetch_db_latest",
                    new=AsyncMock(return_value=None),
                ):
                    with patch(
                        "app.services.market_data_resolver.report_live_bar_source",
                        new=AsyncMock(),
                    ):
                        await fetch_live_bar_with_fallback("EURUSD", "EUR/USD")
@pytest.mark.asyncio
async def test_auto_return_to_twelvedata_after_finnhub() -> None:
    """Finnhub stays active until the next poll succeeds on TwelveData."""
    from app.services.data_source_monitor import report_live_bar_source

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
            "app.services.market_data_resolver.fetch_finnhub_latest_bar",
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

