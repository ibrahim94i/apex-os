"""Unit tests for regime engine."""

from datetime import datetime, timezone

from app.engines.indicator_engine import OHLCVBar
from app.engines.regime_engine import RegimeEngine, get_adx_thresholds
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


def test_get_adx_thresholds_quiet() -> None:
    assert get_adx_thresholds(0.004) == (15.0, 10.0)


def test_get_adx_thresholds_normal() -> None:
    assert get_adx_thresholds(0.01) == (25.0, 20.0)


def test_get_adx_thresholds_violent() -> None:
    assert get_adx_thresholds(0.02) == (25.0, 20.0)


def test_regime_uses_dynamic_thresholds_quiet_market() -> None:
    engine = RegimeEngine()
    close = 5000.0
    bars = [
        OHLCVBar(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=close - 1,
            high=close + 1,
            low=close - 1,
            close=close,
        )
        for _ in range(30)
    ]
    # atr/price = 5/5000 = 0.001 -> quiet thresholds (15, 10); ADX 22 >= 15 -> trend
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        adx=22.0,
        atr=5.0,
        ema_9=51000,
        ema_21=50500,
        ema_50=50000,
    )
    result = engine.classify(bars, indicators, "BTCUSDT")
    assert result.regime == RegimeType.TRENDING_UP


def test_smoothed_atr_volatility_less_noisy_than_spot() -> None:
    engine = RegimeEngine()
    close = 5000.0
    bars = []
    for i in range(40):
        swing = 50.0 if i == 39 else 1.0
        bars.append(
            OHLCVBar(
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                open=close - 1,
                high=close + swing,
                low=close - swing,
                close=close,
            )
        )
    indicators = IndicatorSnapshotSchema(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        atr=100.0,
        adx=20.0,
    )
    smoothed = engine._calc_smoothed_atr_volatility(bars, indicators)
    spot = indicators.atr / close
    assert smoothed < spot
