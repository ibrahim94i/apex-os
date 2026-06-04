"""Per-symbol market snapshot isolation for agent analysis."""

from datetime import datetime, timezone

from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType
from app.services.market_snapshot import (
    bind_indicator_regime_to_symbol,
    build_market_snapshot,
    redis_snapshot_matches_symbol,
)


def test_redis_snapshot_matches_symbol() -> None:
    assert redis_snapshot_matches_symbol("EURUSD", {"symbol": "EURUSD", "rsi": 50.0})
    assert not redis_snapshot_matches_symbol("EURUSD", {"symbol": "XAUUSD", "rsi": 50.0})
    assert redis_snapshot_matches_symbol("XAUUSD", {"rsi": 55.0})


def test_bind_indicator_regime_to_symbol() -> None:
    now = datetime.now(timezone.utc)
    xau_ind = IndicatorSnapshotSchema(
        symbol="XAUUSD", timestamp=now, rsi=55.0, macd=1.2, ema_50=2650.0
    )
    xau_reg = RegimeSnapshotSchema(
        symbol="XAUUSD", timestamp=now, regime=RegimeType.TRENDING_UP, confidence=0.7
    )
    eur_ind = IndicatorSnapshotSchema(
        symbol="EURUSD", timestamp=now, rsi=48.0, macd=0.00012, ema_50=1.09
    )
    eur_reg = RegimeSnapshotSchema(
        symbol="EURUSD", timestamp=now, regime=RegimeType.RANGING, confidence=0.5
    )

    bound_xau_ind, bound_xau_reg = bind_indicator_regime_to_symbol("XAUUSD", xau_ind, xau_reg)
    bound_eur_ind, bound_eur_reg = bind_indicator_regime_to_symbol("EURUSD", eur_ind, eur_reg)

    assert bound_xau_ind.ema_50 == 2650.0
    assert bound_eur_ind.ema_50 == 1.09
    assert bound_xau_ind.symbol == "XAUUSD"
    assert bound_eur_ind.symbol == "EURUSD"
    assert bound_xau_reg.regime == RegimeType.TRENDING_UP
    assert bound_eur_reg.regime == RegimeType.RANGING


import pytest


@pytest.mark.asyncio
async def test_build_market_snapshot_keeps_distinct_prices() -> None:
    from app.schemas.snapshots import KillSwitchStatusSchema
    from app.schemas.enums import KillSwitchStatus

    now = datetime.now(timezone.utc)
    ks = KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE)

    xau_ind = IndicatorSnapshotSchema(symbol="XAUUSD", timestamp=now, rsi=55.0)
    xau_reg = RegimeSnapshotSchema(
        symbol="XAUUSD", timestamp=now, regime=RegimeType.TRENDING_UP, confidence=0.7
    )
    eur_ind = IndicatorSnapshotSchema(symbol="EURUSD", timestamp=now, rsi=48.0)
    eur_reg = RegimeSnapshotSchema(
        symbol="EURUSD", timestamp=now, regime=RegimeType.RANGING, confidence=0.5
    )

    xau_snap = await build_market_snapshot("XAUUSD", 2650.0, xau_ind, xau_reg, ks)
    eur_snap = await build_market_snapshot("EURUSD", 1.085, eur_ind, eur_reg, ks)

    assert xau_snap.symbol == "XAUUSD"
    assert eur_snap.symbol == "EURUSD"
    assert xau_snap.price == 2650.0
    assert eur_snap.price == 1.085
    assert xau_snap.indicators.symbol == "XAUUSD"
    assert eur_snap.indicators.symbol == "EURUSD"
