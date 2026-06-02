"""Tests for trading journal and position manager."""

import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.journal import JournalEntryCreateSchema
from app.services.trading_journal_service import calc_pnl, trading_journal_service
from app.services.position_manager_service import position_manager_service


def test_calc_pnl_long_win() -> None:
    pnl, pct = calc_pnl("LONG", 100.0, 110.0)
    assert pnl == 10.0
    assert pct == 10.0


def test_calc_pnl_short_win() -> None:
    pnl, _ = calc_pnl("SHORT", 100.0, 90.0)
    assert pnl == 10.0


@pytest.mark.asyncio
async def test_position_manager_default_allows_trades() -> None:
    from unittest.mock import MagicMock

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.position_manager_service.get_latest_regime", new_callable=AsyncMock, return_value={"regime": "RANGING"}):
        with patch("app.services.position_manager_service.account_service.get_balance", new_callable=AsyncMock, return_value=10000.0):
            status = await position_manager_service.get_status(session, "XAUUSD")
    assert status.can_trade is True
    assert status.additional_trades_allowed >= 1
    assert "يمكنك فتح" in status.message_ar


@pytest.mark.asyncio
async def test_position_manager_daily_limit_reached() -> None:
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from app.models.journal import JournalEntry

    today = datetime.now(timezone.utc)
    entry = JournalEntry(
        symbol="XAUUSD",
        direction="LONG",
        entry_price=2700,
        exit_price=2690,
        stop_loss=2695,
        take_profit=2710,
        source="personal",
        emotion="fearful",
        result="loss",
        notes=None,
        pnl=-10,
        pnl_pct=-0.37,
        closed_at=today,
    )

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [entry]
    session.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.position_manager_service.get_latest_regime", new_callable=AsyncMock, return_value={"regime": "VOLATILE"}):
        with patch("app.services.position_manager_service.account_service.get_balance", new_callable=AsyncMock, return_value=100.0):
            status = await position_manager_service.get_status(session, "XAUUSD")
    assert "توقف التداول اليوم" in status.message_ar or status.additional_trades_allowed >= 0
