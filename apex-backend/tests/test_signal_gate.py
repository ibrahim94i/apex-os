"""Tests for professional signal gate rules."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.signal_gate import should_emit_new_signal


@pytest.mark.asyncio
async def test_signal_gate_allows_first_signal() -> None:
    with patch("app.services.signal_gate.get_latest_signal", new_callable=AsyncMock, return_value=None):
        allowed, reason = await should_emit_new_signal("BTCUSDT", 95000.0)
    assert allowed is True
    assert reason is None


@pytest.mark.asyncio
async def test_signal_gate_blocks_cooldown() -> None:
    recent = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry_price": 95000.0,
    }
    with patch("app.services.signal_gate.get_latest_signal", new_callable=AsyncMock, return_value=recent):
        allowed, reason = await should_emit_new_signal("BTCUSDT", 95100.0)
    assert allowed is False
    assert reason == "signal_cooldown"


@pytest.mark.asyncio
async def test_signal_gate_blocks_insufficient_gold_move() -> None:
    old = {
        "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "entry_price": 4542.0,
    }
    with patch("app.services.signal_gate.get_latest_signal", new_callable=AsyncMock, return_value=old):
        allowed, reason = await should_emit_new_signal("XAUUSD", 4542.25)
    assert allowed is False
    assert reason == "insufficient_price_move"


@pytest.mark.asyncio
async def test_signal_gate_allows_gold_after_move_and_cooldown() -> None:
    old = {
        "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "entry_price": 4542.0,
    }
    with patch("app.services.signal_gate.get_latest_signal", new_callable=AsyncMock, return_value=old):
        allowed, reason = await should_emit_new_signal("XAUUSD", 4543.0)
    assert allowed is True
    assert reason is None
