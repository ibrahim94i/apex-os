"""Data source monitor — TwelveData primary recovery logging."""

import pytest

from app.services.data_source_monitor import clear_failover_state, report_live_bar_source


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_failover_state()
    yield
    clear_failover_state()


@pytest.mark.asyncio
async def test_report_twelvedata_primary_is_noop_without_prior_failover() -> None:
    await report_live_bar_source("XAUUSD", "twelvedata")
    await report_live_bar_source("XAUUSD", "twelvedata")


@pytest.mark.asyncio
async def test_non_primary_sources_ignored() -> None:
    await report_live_bar_source("XAUUSD", "db")
    await report_live_bar_source("EURUSD", "frankfurter")
