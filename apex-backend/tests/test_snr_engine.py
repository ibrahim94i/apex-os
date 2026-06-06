"""SNR engine tests — pivot levels and confidence adjustment."""

from datetime import datetime, timedelta, timezone

from app.engines.indicator_engine import OHLCVBar
from app.engines.snr_engine import SNREngine, snr_engine
from app.schemas.enums import SignalDirection


def _bars_with_pivots() -> list[OHLCVBar]:
    """Synthetic series: lows at 100, highs at 120, current close 110."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[OHLCVBar] = []
    for i in range(30):
        ts = base + timedelta(hours=i)
        if i % 6 == 2:
            bars.append(OHLCVBar(ts, 108, 120, 107, 115, 0))
        elif i % 6 == 5:
            bars.append(OHLCVBar(ts, 102, 103, 100, 101, 0))
        else:
            bars.append(OHLCVBar(ts, 108, 112, 106, 110, 0))
    return bars


def test_snr_finds_support_and_resistance() -> None:
    engine = SNREngine()
    bars = _bars_with_pivots()
    snr = engine.compute(bars, "XAUUSD")
    assert snr is not None
    assert snr.support_1 is not None
    assert snr.resistance_1 is not None
    assert snr.support_1 < snr.price < snr.resistance_1
    assert snr.distance_to_support_pct is not None
    assert snr.distance_to_resistance_pct is not None


def test_snr_near_resistance_penalizes_long() -> None:
    engine = SNREngine()
    bars = _bars_with_pivots()
    snr = engine.compute(bars, "XAUUSD")
    assert snr is not None
    near_price = snr.resistance_1 * 0.998
    result = engine.adjust_confidence(
        price=near_price,
        prev_close=near_price - 1,
        direction=SignalDirection.LONG,
        confidence=0.80,
        snr=snr,
    )
    assert result.confidence == 0.65
    assert "snr_near_resistance_long_penalty" in result.reasons


def test_snr_bullish_breakout_boosts_long() -> None:
    engine = SNREngine()
    bars = _bars_with_pivots()
    snr = engine.compute(bars, "XAUUSD")
    assert snr is not None
    r1 = snr.resistance_1
    result = engine.adjust_confidence(
        price=r1 + 1,
        prev_close=r1 - 0.5,
        direction=SignalDirection.LONG,
        confidence=0.75,
        snr=snr,
    )
    assert result.confidence == 0.85
    assert "snr_bullish_breakout" in result.reasons


def test_snr_near_support_penalizes_short() -> None:
    engine = SNREngine()
    bars = _bars_with_pivots()
    snr = engine.compute(bars, "XAUUSD")
    assert snr is not None
    near_price = snr.support_1 * 1.002
    result = engine.adjust_confidence(
        price=near_price,
        prev_close=near_price + 1,
        direction=SignalDirection.SHORT,
        confidence=0.80,
        snr=snr,
    )
    assert result.confidence == 0.65
    assert "snr_near_support_short_penalty" in result.reasons


def test_snr_bearish_breakout_boosts_short() -> None:
    engine = SNREngine()
    bars = _bars_with_pivots()
    snr = engine.compute(bars, "XAUUSD")
    assert snr is not None
    s1 = snr.support_1
    result = engine.adjust_confidence(
        price=s1 - 1,
        prev_close=s1 + 0.5,
        direction=SignalDirection.SHORT,
        confidence=0.75,
        snr=snr,
    )
    assert result.confidence == 0.85
    assert "snr_bearish_breakout" in result.reasons


def test_snr_module_singleton() -> None:
    assert snr_engine is not None
