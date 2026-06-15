"""Tests for MetaTrader H1 bootstrap persistence."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.market_data_store import bootstrap_metatrader_h1_bars


def _parsed_bar(hour: int) -> dict:
    ts = datetime(2026, 6, 12, hour, 0, tzinfo=timezone.utc)
    return {
        "timestamp": ts,
        "close_time": datetime(2026, 6, 12, hour + 1, 0, tzinfo=timezone.utc),
        "open": 100.0 + hour,
        "high": 101.0 + hour,
        "low": 99.0 + hour,
        "close": 100.5 + hour,
        "volume": 1.0,
    }


@pytest.mark.asyncio
async def test_bootstrap_deletes_non_metatrader_and_upserts() -> None:
    bars = [_parsed_bar(10), _parsed_bar(11)]
    delete_result = MagicMock()
    delete_result.rowcount = 3
    execute_results = [delete_result, MagicMock()]

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=execute_results)
    session.commit = AsyncMock()

    with patch("app.services.market_data_store.AsyncSessionLocal") as mock_session_local:
        mock_session_local.return_value.__aenter__.return_value = session
        result = await bootstrap_metatrader_h1_bars("XAUUSD", bars)

    assert result["upserted"] == 2
    assert result["deleted"] == 3
    assert result["oldest"] == bars[0]["timestamp"].isoformat()
    assert result["newest"] == bars[1]["timestamp"].isoformat()
    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()
