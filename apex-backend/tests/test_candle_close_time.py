"""Phase 2 — anchor signals to H1 bar close_time; reject unclosed bars."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engines.indicator_engine import OHLCVBar
from app.engines.signal_generator import SignalGenerator
from app.schemas import RegimeType, SignalDirection
from app.schemas.snapshots import IndicatorSnapshotSchema, RegimeSnapshotSchema
from app.services.pipeline import (
    is_closed_h1_bar,
    process_bar,
    resolve_h1_bar_close_time,
)


def test_is_closed_h1_bar_requires_explicit_true() -> None:
    assert is_closed_h1_bar({"is_closed": True}) is True
    assert is_closed_h1_bar({"is_closed": False}) is False
    assert is_closed_h1_bar({}) is False


def test_resolve_h1_bar_close_time_from_close_time_field() -> None:
    raw = {
        "timestamp": "2026-06-17T18:00:00+00:00",
        "close_time": "2026-06-17T19:00:00+00:00",
    }
    assert resolve_h1_bar_close_time(raw) == datetime(
        2026, 6, 17, 19, 0, tzinfo=timezone.utc
    )


def test_resolve_h1_bar_close_time_fallback_open_plus_one_hour() -> None:
    raw = {"timestamp": "2026-06-17T18:00:00+00:00"}
    assert resolve_h1_bar_close_time(raw) == datetime(
        2026, 6, 17, 19, 0, tzinfo=timezone.utc
    )


def test_build_trading_signal_uses_candle_close_time() -> None:
    gen = SignalGenerator()
    close_time = datetime(2026, 6, 17, 19, 0, tzinfo=timezone.utc)
    bars = [
        OHLCVBar(
            timestamp=datetime(2026, 6, 17, 18, 0, tzinfo=timezone.utc),
            open=4300.0,
            high=4310.0,
            low=4295.0,
            close=4305.0,
            volume=1.0,
        )
    ]
    indicators = IndicatorSnapshotSchema(symbol="XAUUSD", timestamp=close_time, rsi=55.0, atr=5.0)
    regime = RegimeSnapshotSchema(
        symbol="XAUUSD",
        timestamp=close_time,
        regime=RegimeType.TRENDING_UP,
        confidence=0.8,
        adx_value=30.0,
        volatility_pct=0.5,
        trend_strength=0.3,
    )
    signal, _ = gen.build_trading_signal(
        bars,
        "XAUUSD",
        SignalDirection.LONG,
        0.9,
        indicators,
        regime,
        require_min_confidence=False,
        candle_close_time=close_time,
    )
    assert signal is not None
    assert signal.timestamp == close_time


@pytest.mark.asyncio
async def test_process_bar_skips_unclosed_bar_before_persist() -> None:
    raw_bar = {
        "symbol": "XAUUSD",
        "timestamp": "2026-06-17T18:00:00+00:00",
        "open": 4300.0,
        "high": 4310.0,
        "low": 4295.0,
        "close": 4305.0,
        "volume": 1.0,
        "source": "metatrader",
        "is_closed": False,
    }
    with patch(
        "app.services.pipeline.pipeline_blocked_by_market_hours",
        return_value=False,
    ):
        with patch("app.services.pipeline._persist_bar", new=AsyncMock()) as mock_persist:
            await process_bar(raw_bar)
    mock_persist.assert_not_called()
