"""Tests for data source failover monitoring and Telegram alerts."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.data_source_monitor import clear_failover_state, report_live_bar_source


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_failover_state()
    yield
    clear_failover_state()


@pytest.mark.asyncio
async def test_failover_sends_telegram_once() -> None:
    with patch(
        "app.services.telegram_notifier.telegram_notifier.send_data_source_failover_alert",
        new=AsyncMock(return_value=True),
    ) as mock_alert:
        await report_live_bar_source("XAUUSD", "frankfurter")
        await report_live_bar_source("XAUUSD", "frankfurter")
    mock_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_primary_recovery_clears_failover_state() -> None:
    with patch(
        "app.services.telegram_notifier.telegram_notifier.send_data_source_failover_alert",
        new=AsyncMock(return_value=True),
    ):
        with patch(
            "app.services.telegram_notifier.telegram_notifier.send_data_source_recovery_alert",
            new=AsyncMock(return_value=True),
        ) as mock_recovery:
            await report_live_bar_source("EURUSD", "frankfurter")
            await report_live_bar_source("EURUSD", "twelvedata")
    mock_recovery.assert_awaited_once()
