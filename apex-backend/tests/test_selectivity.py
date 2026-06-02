"""Tests for High Selectivity Mode filters."""

from datetime import datetime, timezone

from app.engines.indicator_engine import OHLCVBar
from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.services.market_hours import is_gold_trading_session
from app.services.selectivity import effective_min_confidence_pct
from app.services.signal_filters import check_confluence, check_regime_filter


def _indicators(**kwargs) -> IndicatorSnapshotSchema:
    base = dict(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        rsi=50.0,
        macd=1.0,
        macd_signal=0.5,
        ema_50=2100.0,
        ema_200=2000.0,
        atr=5.0,
        atr_avg_20=4.0,
    )
    base.update(kwargs)
    return IndicatorSnapshotSchema(**base)


def _regime(regime: RegimeType, **kwargs) -> RegimeSnapshotSchema:
    base = dict(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        regime=regime,
        confidence=0.8,
        adx_value=30.0,
        volatility_pct=1.0,
        trend_strength=0.5,
    )
    base.update(kwargs)
    return RegimeSnapshotSchema(**base)


def test_effective_confidence_learning_period() -> None:
    assert effective_min_confidence_pct() == 70.0


def test_confluence_long_passes() -> None:
    ok, reason = check_confluence(SignalDirection.LONG, _indicators())
    assert ok is True
    assert reason is None


def test_confluence_fails_rsi() -> None:
    ok, reason = check_confluence(SignalDirection.LONG, _indicators(rsi=70.0))
    assert ok is False
    assert reason == "rsi_out_of_range"


def test_regime_blocks_ranging() -> None:
    ok, reason = check_regime_filter(SignalDirection.LONG, _regime(RegimeType.RANGING))
    assert ok is False


def test_regime_allows_trending() -> None:
    ok, _ = check_regime_filter(SignalDirection.LONG, _regime(RegimeType.TRENDING_UP))
    assert ok is True


def test_gold_session_london_hours() -> None:
    from zoneinfo import ZoneInfo

    baghdad = ZoneInfo("Asia/Baghdad")
    # Monday 12:00 Baghdad
    dt = datetime(2026, 6, 1, 12, 0, tzinfo=baghdad).astimezone(timezone.utc)
    assert is_gold_trading_session(dt) is True
