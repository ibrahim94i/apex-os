"""Tests for price_bars guardrails and MetaTrader-only agent reads."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.market_data_store import (
    AGENT_BAR_SOURCE,
    fetch_agent_bars_from_db,
    purge_non_metatrader_price_bars,
)
from app.services.price_bar_guard import should_block_external_price_bars


@pytest.mark.asyncio
async def test_should_block_external_price_bars_when_mt_price_fresh() -> None:
    fresh_mt = {"received_at": datetime.now(timezone.utc).isoformat()}
    with patch(
        "app.core.cache.get_metatrader_price",
        new=AsyncMock(return_value=fresh_mt),
    ):
        assert await should_block_external_price_bars("XAUUSD") is True


@pytest.mark.asyncio
async def test_should_not_block_external_price_bars_when_mt_stale() -> None:
    stale_mt = {"received_at": "2020-01-01T00:00:00+00:00"}
    with patch(
        "app.core.cache.get_metatrader_price",
        new=AsyncMock(return_value=stale_mt),
    ):
        assert await should_block_external_price_bars("XAUUSD") is False


@pytest.mark.asyncio
async def test_fetch_agent_bars_from_db_filters_source() -> None:
    with patch(
        "app.services.market_data_store.fetch_bars_from_db",
        new=AsyncMock(return_value=[]),
    ) as mock_fetch:
        await fetch_agent_bars_from_db("XAUUSD", 100)
    mock_fetch.assert_awaited_once_with("XAUUSD", 100, source=AGENT_BAR_SOURCE)


@pytest.mark.asyncio
async def test_persist_bar_skips_external_when_mt_price_connected() -> None:
    from app.services.pipeline import _persist_bar

    session = MagicMock()
    session.execute = AsyncMock()
    bar = {
        "symbol": "XAUUSD",
        "source": "twelvedata",
        "timestamp": "2026-06-15T19:00:00+00:00",
        "open": 1.0,
        "high": 2.0,
        "low": 1.0,
        "close": 1.5,
        "volume": 0.0,
    }
    with patch(
        "app.services.price_bar_guard.should_block_external_price_bars",
        new=AsyncMock(return_value=True),
    ):
        with patch(
            "app.services.price_bar_guard.log_blocked_external_bar",
            new=AsyncMock(),
        ):
            await _persist_bar(session, bar)
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_purge_non_metatrader_price_bars_executes_delete() -> None:
    session = MagicMock()
    result = MagicMock()
    result.rowcount = 3
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    with patch(
        "app.services.market_data_store.AsyncSessionLocal",
    ) as mock_session_local:
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        deleted = await purge_non_metatrader_price_bars("XAUUSD")

    assert deleted == 3
    session.commit.assert_awaited_once()
