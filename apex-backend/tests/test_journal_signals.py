"""Telegram signal journal auto-log and follow-up."""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas import SignalDirection, TradingSignalSchema
from app.schemas.enums import RegimeType
from app.schemas.journal import JournalFollowUpSchema
from app.services.trading_journal_service import trading_journal_service


def _signal(**kwargs) -> TradingSignalSchema:
    base = dict(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        direction=SignalDirection.LONG,
        confidence=0.82,
        entry_price=2700.0,
        stop_loss=2690.0,
        take_profit=2720.0,
        regime=RegimeType.TRENDING_UP,
        snr_state="inside_zone",
        snr_penalty=-20,
    )
    base.update(kwargs)
    return TradingSignalSchema(**base)


@pytest.mark.asyncio
async def test_record_telegram_signal_pending() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda e: setattr(e, "id", 1))

    schema = await trading_journal_service.record_telegram_signal(session, _signal())
    assert schema.follow_up_status == "pending"
    assert schema.source == "system_signal"
    assert schema.result == "pending"
    assert schema.snr_state == "inside_zone"
    assert schema.snr_penalty == -20


def _pending_entry(**kwargs) -> "JournalEntry":
    from app.models.journal import JournalEntry

    defaults = dict(
        id=1,
        symbol="XAUUSD",
        direction="LONG",
        entry_price=100.0,
        exit_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        source="system_signal",
        emotion="hesitant",
        result="pending",
        follow_up_status="pending",
        notes="test",
        pnl=0.0,
        pnl_pct=0.0,
        closed_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return JournalEntry(**defaults)


@pytest.mark.asyncio
async def test_follow_up_entered_win() -> None:
    entry = _pending_entry()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = entry
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    data = JournalFollowUpSchema(action="entered", exit_price=110.0, result="win")
    out = await trading_journal_service.apply_follow_up(session, 1, data)
    assert out.follow_up_status == "entered"
    assert out.result == "win"
    assert out.pnl == 10.0


@pytest.mark.asyncio
async def test_follow_up_ignored() -> None:
    entry = _pending_entry(id=2, notes="")

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = entry
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    out = await trading_journal_service.apply_follow_up(
        session, 2, JournalFollowUpSchema(action="ignored")
    )
    assert out.follow_up_status == "ignored"
    assert out.pnl == 0.0


@pytest.mark.asyncio
async def test_signal_report_counts() -> None:
    from app.models.journal import JournalEntry

    entries = [
        JournalEntry(
            symbol="XAUUSD",
            direction="LONG",
            entry_price=100,
            exit_price=110,
            stop_loss=95,
            take_profit=115,
            source="system_signal",
            emotion="hesitant",
            result="win",
            follow_up_status="entered",
            pnl=10,
            pnl_pct=10,
            closed_at=datetime.now(timezone.utc),
        ),
        JournalEntry(
            symbol="EURUSD",
            direction="SHORT",
            entry_price=1.1,
            exit_price=1.1,
            stop_loss=1.12,
            take_profit=1.08,
            source="system_signal",
            emotion="hesitant",
            result="neutral",
            follow_up_status="ignored",
            pnl=0,
            pnl_pct=0,
            closed_at=datetime.now(timezone.utc),
        ),
        JournalEntry(
            symbol="USDJPY",
            direction="LONG",
            entry_price=150,
            exit_price=150,
            stop_loss=149,
            take_profit=152,
            source="system_signal",
            emotion="hesitant",
            result="pending",
            follow_up_status="pending",
            pnl=0,
            pnl_pct=0,
            closed_at=datetime.now(timezone.utc),
        ),
    ]
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = entries
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    report = await trading_journal_service.get_signal_report(session)
    assert report.total_signals == 3
    assert report.entered_count == 1
    assert report.ignored_count == 1
    assert report.pending_count == 1
    assert report.win_rate == 1.0
    assert report.total_profit == 10.0
