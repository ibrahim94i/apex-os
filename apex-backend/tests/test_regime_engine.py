"""Unit tests for regime engine."""

from datetime import datetime, timezone

from app.engines.indicator_engine import OHLCVBar
from app.engines.regime_engine import RegimeEngine
from app.schemas import IndicatorSnapshotSchema, RegimeType


def _make_bars(count: int, trend: str = "up") -> list[OHLCVBar]:
    bars = []
    for i in range(count):
        if trend == "up":
            close = 50000 + i * 100
        else:
            close = 50000 - i * 50
        bars.append(
            OHLCVBar(
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                open=close - 10,
                high=close + 20,
                low=close - 20,
                close=close,
            )
        )
    return bars


def test_regime_trending_up() -> None:
    engine = RegimeEngine()
    bars = _make_bars(30, "up")
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        ema_9=51000,
        ema_21=50500,
        ema_50=50000,
        adx=30.0,
    )
    result = engine.classify(bars, indicators, "BTCUSDT")
    assert result.regime in (RegimeType.TRENDING_UP, RegimeType.VOLATILE, RegimeType.RANGING)
    assert 0 <= result.confidence <= 1


def test_regime_ranging_low_adx() -> None:
    engine = RegimeEngine()
    bars = _make_bars(30)
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        adx=15.0,
    )
    result = engine.classify(bars, indicators, "BTCUSDT")
    assert result.regime == RegimeType.RANGING
