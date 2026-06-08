"""Signal build uses collective confidence for floor, SNR-adjusted for signal confidence."""

from datetime import datetime, timezone

import pytest

from app.engines.indicator_engine import OHLCVBar
from app.engines.signal_generator import SignalGenerator
from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType, SignalDirection


def _bars() -> list[OHLCVBar]:
    now = datetime.now(timezone.utc)
    return [
        OHLCVBar(
            timestamp=now,
            open=2700.0 - i,
            high=2701.0 - i,
            low=2699.0 - i,
            close=2700.0 - i,
            volume=100.0,
        )
        for i in range(60)
    ]


def _indicators() -> IndicatorSnapshotSchema:
    now = datetime.now(timezone.utc)
    return IndicatorSnapshotSchema(
        symbol="XAUUSD",
        timestamp=now,
        rsi=40.0,
        macd=-0.5,
        macd_signal=-0.2,
        ema_50=2680.0,
        ema_200=2720.0,
        atr=2.0,
        atr_avg_20=2.0,
        adx=35.0,
    )


def _regime() -> RegimeSnapshotSchema:
    now = datetime.now(timezone.utc)
    return RegimeSnapshotSchema(
        symbol="XAUUSD",
        timestamp=now,
        regime=RegimeType.TRENDING_DOWN,
        confidence=0.8,
        adx_value=35.0,
    )


def test_snr_adjusted_confidence_builds_when_collective_above_floor() -> None:
    gen = SignalGenerator()
    signal, reason = gen.build_trading_signal(
        _bars(),
        "XAUUSD",
        SignalDirection.SHORT,
        0.5784,
        _indicators(),
        _regime(),
        require_min_confidence=True,
        min_confidence=0.70,
        collective_confidence=0.7284,
    )
    assert reason is None
    assert signal is not None
    assert signal.confidence <= 0.5784
    assert signal.direction == SignalDirection.SHORT


def test_rejects_when_collective_below_floor_even_if_signal_confidence_high() -> None:
    gen = SignalGenerator()
    signal, reason = gen.build_trading_signal(
        _bars(),
        "XAUUSD",
        SignalDirection.SHORT,
        0.80,
        _indicators(),
        _regime(),
        require_min_confidence=True,
        min_confidence=0.70,
        collective_confidence=0.65,
    )
    assert signal is None
    assert reason == "confidence_below_threshold"


def test_rejects_snr_only_confidence_without_collective_override() -> None:
    gen = SignalGenerator()
    signal, reason = gen.build_trading_signal(
        _bars(),
        "XAUUSD",
        SignalDirection.SHORT,
        0.5784,
        _indicators(),
        _regime(),
        require_min_confidence=True,
        min_confidence=0.70,
    )
    assert signal is None
    assert reason == "confidence_below_threshold"
