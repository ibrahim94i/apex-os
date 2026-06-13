"""SNR engine tests — ±0.25% level zones, confirmed breakouts."""

from datetime import datetime, timedelta, timezone

import pytest

from app.engines.indicator_engine import OHLCVBar
from app.engines.snr_engine import SNREngine, snr_engine
from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRSnapshotSchema
from app.utils.price_zones import level_zone_bounds


def _bars_with_pivots() -> list[OHLCVBar]:
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
    engine = SNREngine()
    snr = SNRSnapshotSchema(**defaults)
    return snr.model_copy(
        update={
            "support_1_zone": engine._make_zone(snr.support_1),
            "support_2_zone": engine._make_zone(snr.support_2),
            "support_3_zone": engine._make_zone(snr.support_3),
            "resistance_1_zone": engine._make_zone(snr.resistance_1),
            "resistance_2_zone": engine._make_zone(snr.resistance_2),
            "resistance_3_zone": engine._make_zone(snr.resistance_3),
        }
    )


def test_snr_finds_support_and_resistance() -> None:
    engine = SNREngine()
    bars = _bars_with_pivots()
    snr = engine.compute(bars, "XAUUSD")
    assert snr is not None
    assert snr.support_1 is not None
    assert snr.resistance_1 is not None
    assert snr.support_1_zone is not None
    assert snr.resistance_1_zone is not None
    assert snr.support_1 < snr.price < snr.resistance_1


def test_price_inside_s1_zone_blocks() -> None:
    engine = SNREngine()
    snr = _snr(support_1=105.0, price=105.0)
    bars = [OHLCVBar(datetime(2026, 1, 1, tzinfo=timezone.utc), 104, 106, 104, 105.0, 0)]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.SHORT,
        confidence=0.80,
        snr=snr,
    )
    assert result.block_signal is True
    assert result.block_reason == "snr_in_s1_zone"
    assert result.category == "snr_zone"


def test_price_inside_r1_zone_blocks() -> None:
    engine = SNREngine()
    snr = _snr(resistance_1=115.0, price=115.0)
    bars = [OHLCVBar(datetime(2026, 1, 1, tzinfo=timezone.utc), 114, 116, 114, 115.0, 0)]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.LONG,
        confidence=0.80,
        snr=snr,
    )
    assert result.block_signal is True
    assert result.block_reason == "snr_in_r1_zone"


def test_bullish_breakout_requires_confirmation_above_r1_zone() -> None:
    engine = SNREngine()
    r1 = 115.0
    _, r1_high = level_zone_bounds(r1)
    snr = _snr(resistance_1=r1, support_1=100.0, price=r1_high + 1.0)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        OHLCVBar(base, r1_high - 0.5, r1_high + 0.2, r1_high - 0.8, r1_high + 0.1, 0),
        OHLCVBar(base + timedelta(hours=1), r1_high + 0.05, r1_high + 0.3, r1_high, r1_high + 0.05, 0),
    ]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.LONG,
        confidence=0.75,
        snr=snr,
    )
    assert "snr_bullish_breakout" not in result.reasons

    bars_confirmed = [
        OHLCVBar(base, r1_high - 0.5, r1_high + 0.5, r1_high - 0.8, r1_high + 0.4, 0),
        OHLCVBar(base + timedelta(hours=1), r1_high + 0.3, r1_high + 1.0, r1_high + 0.2, r1_high + 0.9, 0),
    ]
    result_ok = engine.evaluate_signal(
        bars=bars_confirmed,
        direction=SignalDirection.LONG,
        confidence=0.75,
        snr=snr,
    )
    assert result_ok.confidence == 0.85
    assert "snr_bullish_breakout" in result_ok.reasons
    assert "Bullish Breakout" in (result_ok.explain_ar or "")


def test_bearish_breakout_requires_confirmation_below_s1_zone() -> None:
    engine = SNREngine()
    s1 = 105.0
    s1_low, _ = level_zone_bounds(s1)
    snr = _snr(support_1=s1, resistance_1=120.0, price=s1_low - 1.0)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        OHLCVBar(base, s1_low + 0.5, s1_low + 0.8, s1_low + 0.2, s1_low + 0.4, 0),
        OHLCVBar(base + timedelta(hours=1), s1_low + 0.1, s1_low + 0.4, s1_low, s1_low + 0.2, 0),
    ]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.SHORT,
        confidence=0.75,
        snr=snr,
    )
    assert "snr_bearish_breakout" not in result.reasons

    bars_confirmed = [
        OHLCVBar(base, s1_low + 0.5, s1_low + 0.6, s1_low - 0.2, s1_low - 0.1, 0),
        OHLCVBar(base + timedelta(hours=1), s1_low - 0.2, s1_low, s1_low - 1.0, s1_low - 0.8, 0),
    ]
    result_ok = engine.evaluate_signal(
        bars=bars_confirmed,
        direction=SignalDirection.SHORT,
        confidence=0.75,
        snr=snr,
    )
    assert result_ok.confidence == 0.85
    assert "snr_bearish_breakout" in result_ok.reasons
    assert "S1" in (result_ok.explain_ar or "")


def test_near_resistance_rejection_penalizes_long_below_r1() -> None:
    engine = SNREngine()
    snr = _snr(resistance_1=115.0, price=114.43)
    bars = [OHLCVBar(datetime(2026, 1, 1, tzinfo=timezone.utc), 114.2, 114.5, 114.1, 114.43, 0)]
    result = engine.evaluate_signal(
        bars=bars,
        direction=SignalDirection.LONG,
        confidence=0.80,
        snr=snr,
    )
    assert result.confidence == 0.65
    assert result.category == "rejection"


def test_snr_module_singleton() -> None:
    assert snr_engine is not None


def test_snr_fallback_levels_when_no_pivots() -> None:
    """Monotonic flat bars produce no pivots — fallback uses range extrema."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[OHLCVBar] = []
    for i in range(39):
        price = 2650.0 + i * 0.5
        bars.append(
            OHLCVBar(
                base + timedelta(hours=i),
                price,
                price,
                price,
                price,
                0,
            )
        )
    pullback = 2665.0
    bars.append(
        OHLCVBar(
            base + timedelta(hours=39),
            pullback,
            pullback,
            pullback,
            pullback,
            0,
        )
    )

    snr = snr_engine.compute(bars, "XAUUSD")
    assert snr is not None
    assert snr.support_1 is not None
    assert snr.resistance_1 is not None
    assert snr.support_1 < snr.price < snr.resistance_1


def test_snr_compute_uses_current_price_override() -> None:
    """Live MetaTrader price overrides last bar close for SNR distance math."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[OHLCVBar] = []
    for i in range(39):
        price = 2650.0 + i * 0.5
        bars.append(
            OHLCVBar(
                base + timedelta(hours=i),
                price,
                price,
                price,
                price,
                0,
            )
        )
    last_close = 2665.0
    bars.append(
        OHLCVBar(
            base + timedelta(hours=39),
            last_close,
            last_close,
            last_close,
            last_close,
            0,
        )
    )

    mt_price = 2675.0
    snr_default = snr_engine.compute(bars, "XAUUSD")
    snr_mt = snr_engine.compute(bars, "XAUUSD", current_price=mt_price)

    assert snr_default is not None
    assert snr_mt is not None
    assert snr_default.price == pytest.approx(last_close)
    assert snr_mt.price == pytest.approx(mt_price)
