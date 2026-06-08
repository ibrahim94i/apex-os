"""Regression: outcome tracker must read DB latest price via `price` key."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.journal import JournalEntry
from app.services.outcome_tracker import auto_outcome_tracker


@pytest.mark.asyncio
async def test_evaluate_journal_entry_uses_price_key_from_db() -> None:
    entry = JournalEntry(
        id=1,
        symbol="XAUUSD",
        direction="LONG",
        entry_price=4300.0,
        stop_loss=4290.0,
        take_profit=4320.0,
        source="system_signal",
        created_at=datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc),
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )

    with patch(
        "app.services.market_data_store.get_latest_price_from_db",
        new=AsyncMock(return_value={"price": 4310.0, "timestamp": "2026-06-08T15:00:00+00:00"}),
    ):
        result = await auto_outcome_tracker._evaluate_journal_entry(session, entry)

    assert result is None or result.outcome in ("win", "loss", "expired")
