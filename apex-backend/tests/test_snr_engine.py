"""SNR engine tests — zones, confirmed breakouts, explainability."""

from datetime import datetime, timedelta, timezone

from app.engines.indicator_engine import OHLCVBar
from app.engines.snr_engine import SNREngine, snr_engine
from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRSnapshotSchema


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


def _snr(**kwargs: float) -> SNRSnapshotSchema:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    defaults = {
        "symbol": "XAUUSD",
        "timestamp": now,
        "price": 110.0,
        "support_1": 105.0,
        "support_2": 100.0,
        "resistance_1": 115.0,
        "resistance_2": 120.0,
    }
    defaults.update(kwargs)
    return SNRSnapshotSchema(**defaults)


def test_snr_finds_support_and_resistance() -> None:
    engine = SNREngine()
    bars = _bars_with_pivots()
    snr = engine.compute(bars, "XAUUSD")
    assert snr is not None
    assert snr.support_1 is not None
    assert snr.resistance_1 is not None
    assert snr.support_1 < snr.price < snr.resistance_1


def test_no_trade_zone_between_s1_s2_blocks() -> None:
    engine = SNREngine()
    snr = _snr(support_1=105.0, support_2=100.0, price=102.0)
    bars = [OHLCVBar(datetime(2026, 1, 1, tzinfo=timezone.utc), 101, 103, 100, 102, 0)]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.LONG,
        confidence=0.80,
        snr=snr,
    )
    assert result.block_signal is True
    assert result.block_reason == "snr_no_trade_zone_support"
    assert result.category == "snr_zone"
    assert "SNR Zone" in (result.explain_ar or "")


def test_no_trade_zone_between_r1_r2_blocks() -> None:
    engine = SNREngine()
    snr = _snr(resistance_1=115.0, resistance_2=120.0, price=117.0)
    bars = [OHLCVBar(datetime(2026, 1, 1, tzinfo=timezone.utc), 116, 118, 115, 117, 0)]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.SHORT,
        confidence=0.80,
        snr=snr,
    )
    assert result.block_signal is True
    assert result.block_reason == "snr_no_trade_zone_resistance"
    assert result.category == "snr_zone"


def test_bullish_breakout_requires_confirmation_candle() -> None:
    engine = SNREngine()
    snr = _snr(resistance_1=115.0, resistance_2=None, support_1=100.0, support_2=None, price=116.0)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Only breakout bar — no confirmation
    bars = [
        OHLCVBar(base, 114, 116, 113, 116, 0),
        OHLCVBar(base + timedelta(hours=1), 115, 116.5, 114, 115.5, 0),
    ]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.LONG,
        confidence=0.75,
        snr=snr,
    )
    assert "snr_bullish_breakout" not in result.reasons
    assert result.confidence == 0.75

    bars_confirmed = [
        OHLCVBar(base, 114, 116, 113, 116, 0),
        OHLCVBar(base + timedelta(hours=1), 115.5, 117, 115, 116.5, 0),
    ]
    result_ok = engine.evaluate_signal(
        bars=bars_confirmed,
        direction=SignalDirection.LONG,
        confidence=0.75,
        snr=snr,
    )
    assert result_ok.confidence == 0.85
    assert "snr_bullish_breakout" in result_ok.reasons
    assert result_ok.category == "breakout"
    assert "Bullish Breakout" in (result_ok.explain_ar or "")


def test_bearish_breakout_requires_confirmation_candle() -> None:
    engine = SNREngine()
    snr = _snr(support_1=105.0, support_2=None, resistance_1=120.0, resistance_2=None, price=104.0)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        OHLCVBar(base, 106, 107, 104, 104, 0),
        OHLCVBar(base + timedelta(hours=1), 104, 105, 103.5, 104.2, 0),
    ]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.SHORT,
        confidence=0.75,
        snr=snr,
    )
    assert "snr_bearish_breakout" not in result.reasons

    bars_confirmed = [
        OHLCVBar(base, 106, 107, 104, 104, 0),
        OHLCVBar(base + timedelta(hours=1), 104, 104.5, 103, 103.5, 0),
    ]
    result_ok = engine.evaluate_signal(
        bars=bars_confirmed,
        direction=SignalDirection.SHORT,
        confidence=0.75,
        snr=snr,
    )
    assert result_ok.confidence == 0.85
    assert "snr_bearish_breakout" in result_ok.reasons
    assert "Bearish Breakout" in (result_ok.explain_ar or "")
    assert "S1" in (result_ok.explain_ar or "")


def test_near_resistance_rejection_penalizes_long() -> None:
    engine = SNREngine()
    snr = _snr(resistance_1=115.0, price=114.5)
    bars = [OHLCVBar(datetime(2026, 1, 1, tzinfo=timezone.utc), 114, 115, 114, 114.5, 0)]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.LONG,
        confidence=0.80,
        snr=snr,
    )
    assert result.confidence == 0.65
    assert result.category == "rejection"
    assert "Rejection" in (result.explain_ar or "")


def test_near_support_rejection_penalizes_short() -> None:
    engine = SNREngine()
    snr = _snr(support_1=105.0, price=105.4)
    bars = [OHLCVBar(datetime(2026, 1, 1, tzinfo=timezone.utc), 105, 106, 105, 105.4, 0)]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.SHORT,
        confidence=0.80,
        snr=snr,
    )
    assert result.confidence == 0.65
    assert result.category == "rejection"
    assert "Rejection" in (result.explain_ar or "")


def test_snr_module_singleton() -> None:
    assert snr_engine is not None
