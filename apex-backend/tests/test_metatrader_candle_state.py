"""Tests for MetaTrader candle state preservation on non-H1 ingest."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.metatrader_candle_service import ingest_metatrader_candle


@pytest.mark.asyncio
async def test_m5_ingest_preserves_h1_last_candle_at() -> None:
    h1_ts = datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc)
    existing = {
        "last_candle_at": h1_ts.isoformat(),
        "close_time": datetime(2026, 6, 15, 17, 0, tzinfo=timezone.utc).isoformat(),
        "bootstrapped_at": datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc).isoformat(),
        "bootstrap_count": 500,
        "timeframes": {
            "H1": {"last_candle_at": h1_ts.isoformat()},
        },
    }
    captured: dict = {}

    async def fake_set_state(symbol: str, state: dict) -> None:
        captured["state"] = state

    parsed = {
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "timestamp": datetime(2026, 6, 15, 17, 50, tzinfo=timezone.utc),
        "close_time": datetime(2026, 6, 15, 17, 55, tzinfo=timezone.utc),
        "open": 4356.0,
        "high": 4357.0,
        "low": 4355.0,
        "close": 4356.5,
        "volume": 100.0,
    }

    with patch(
        "app.services.metatrader_candle_service.upsert_chart_bar",
        new=AsyncMock(),
    ):
        with patch(
            "app.core.cache.get_metatrader_candle_state",
            new=AsyncMock(return_value=existing),
        ):
            with patch(
                "app.services.metatrader_candle_service.set_metatrader_candle_state",
                side_effect=fake_set_state,
            ):
                await ingest_metatrader_candle(parsed)

    assert captured["state"]["last_candle_at"] == h1_ts.isoformat()
    assert captured["state"]["bootstrap_count"] == 500
    assert captured["state"]["timeframes"]["M5"]["last_candle_at"] == parsed["timestamp"].isoformat()
