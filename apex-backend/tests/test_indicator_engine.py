"""Unit tests for indicator engine."""

from datetime import datetime, timedelta, timezone

import pytest

from app.engines.indicator_engine import IndicatorEngine, OHLCVBar


def _generate_bars(count: int, base_price: float = 50000.0) -> list[OHLCVBar]:
    bars = []
    for i in range(count):
        price = base_price + (i * 10) + (i % 5) * 50
        bars.append(
            OHLCVBar(
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
                open=price - 5,
                high=price + 10,
                low=price - 10,
                close=price,
                volume=100.0,
            )
        )
    return bars


def test_indicator_engine_insufficient_bars() -> None:
    engine = IndicatorEngine(min_bars=50)
    bars = _generate_bars(30)
    result = engine.compute(bars, "BTCUSDT")
    assert result is None


def test_indicator_engine_computes_all_indicators() -> None:
    engine = IndicatorEngine(min_bars=50)
    bars = _generate_bars(60)
    result = engine.compute(bars, "BTCUSDT")
    assert result is not None
    assert result.symbol == "BTCUSDT"
    assert result.rsi is not None
    assert 0 <= result.rsi <= 100
    assert result.macd is not None
    assert result.ema_9 is not None
    assert result.ema_21 is not None
    assert result.ema_50 is not None
    assert result.atr is not None
    assert result.adx is not None
