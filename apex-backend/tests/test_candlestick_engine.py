"""Candlestick pattern detection tests."""

from datetime import datetime, timedelta, timezone

from app.engines.candlestick_engine import candlestick_engine
from app.engines.indicator_engine import OHLCVBar
from app.services.market_snapshot import build_market_snapshot
from app.schemas import KillSwitchStatusSchema, RegimeSnapshotSchema, RegimeType
from app.schemas.agent import CandlestickPatternSchema
from app.schemas.snapshots import IndicatorSnapshotSchema


def _bar(
    i: int,
    o: float,
    h: float,
    l: float,
    c: float,
    *,
    base: datetime | None = None,
) -> OHLCVBar:
    ts = (base or datetime(2026, 6, 1, tzinfo=timezone.utc)) + timedelta(hours=i)
    return OHLCVBar(timestamp=ts, open=o, high=h, low=l, close=c)


def _flat_bars(n: int = 10, price: float = 100.0) -> list[OHLCVBar]:
    return [_bar(i, price, price + 0.5, price - 0.5, price) for i in range(n)]


def test_detect_doji_on_flat_candle() -> None:
    bars = _flat_bars(9)
    bars.append(_bar(9, 100.0, 100.05, 99.95, 100.01))
    patterns = candlestick_engine.detect(bars)
    ids = {p.pattern for p in patterns}
    assert "DOJI" in ids


def test_detect_bullish_engulfing() -> None:
    bars = _flat_bars(8)
    bars.append(_bar(8, 102.0, 102.5, 100.5, 101.0))
    bars.append(_bar(9, 100.5, 104.0, 100.0, 103.5))
    patterns = candlestick_engine.detect(bars)
    assert any(p.pattern == "BULLISH_ENGULFING" for p in patterns)


def test_detect_hammer_shape() -> None:
    bars = _flat_bars(9)
    bars.append(_bar(9, 99.0, 101.5, 90.0, 101.0))
    patterns = candlestick_engine.detect(bars)
    assert any(p.pattern == "HAMMER" for p in patterns)


import pytest


@pytest.mark.asyncio
async def test_market_snapshot_includes_candlestick_patterns() -> None:
    now = datetime.now(timezone.utc)
    ind = IndicatorSnapshotSchema(symbol="EURUSD", timestamp=now, rsi=50.0)
    reg = RegimeSnapshotSchema(
        symbol="EURUSD",
        timestamp=now,
        regime=RegimeType.RANGING,
        confidence=0.5,
    )
    ks = KillSwitchStatusSchema(status="INACTIVE")
    custom = [
        CandlestickPatternSchema(
            pattern="DOJI",
            name_ar="دوجي",
            signal="neutral",
        )
    ]
    snap = await build_market_snapshot(
        "EURUSD",
        1.08,
        ind,
        reg,
        ks,
        candlestick_patterns=custom,
    )
    assert len(snap.candlestick_patterns) == 1
    assert snap.candlestick_patterns[0].pattern == "DOJI"


def test_candlestick_block_in_market_analyst_prompt() -> None:
    from app.agents.market_analyst.prompt import build_user_prompt
    from app.schemas.agent import MarketSnapshot

    now = datetime.now(timezone.utc)
    snap = MarketSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        price=2700.0,
        indicators=IndicatorSnapshotSchema(symbol="XAUUSD", timestamp=now, rsi=45.0),
        regime=RegimeSnapshotSchema(
            symbol="XAUUSD",
            timestamp=now,
            regime=RegimeType.RANGING,
            confidence=0.5,
        ),
        kill_switch=KillSwitchStatusSchema(status="INACTIVE"),
        account_balance=10000.0,
        max_risk_pct=1.0,
        max_drawdown_pct=5.0,
        candlestick_patterns=[
            CandlestickPatternSchema(
                pattern="HAMMER",
                name_ar="مطرقة",
                signal="bullish",
            )
        ],
    )
    prompt = build_user_prompt(snap)
    assert "أنماط الشمعات" in prompt
    assert "مطرقة" in prompt
