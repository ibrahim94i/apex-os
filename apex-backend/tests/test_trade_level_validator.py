"""Unit tests for zone-based SL/TP and Trade Level Validator."""

from datetime import datetime, timezone

from app.engines.sl_tp_engine import SLTPEngine
from app.engines.trade_level_validator import validate_trade_levels
from app.schemas import IndicatorSnapshotSchema, RegimeType, SignalDirection


def _indicators(*, symbol: str = "XAUUSD", atr: float = 5.0) -> IndicatorSnapshotSchema:
    return IndicatorSnapshotSchema(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        atr=atr,
    )


def test_sl_tp_buy_uses_zone_bounds() -> None:
    engine = SLTPEngine()
    zone_low, zone_high = 2693.25, 2706.75
    result = engine.calculate(
        zone_low,
        zone_high,
        SignalDirection.LONG,
        _indicators(atr=5.0),
    )
    assert result.stop_loss == zone_low - 5.0
    assert result.take_profit == zone_high + 10.0
    assert result.entry_price == 2700.0


def test_sl_tp_sell_uses_zone_bounds() -> None:
    engine = SLTPEngine()
    zone_low, zone_high = 2693.25, 2706.75
    result = engine.calculate(
        zone_low,
        zone_high,
        SignalDirection.SHORT,
        _indicators(atr=5.0),
    )
    assert result.stop_loss == zone_high + 5.0
    assert result.take_profit == zone_low - 10.0


def test_buy_valid_trade_levels() -> None:
    zone_low, zone_high = 100.0, 110.0
    entry_price = 105.0
    atr = 5.0
    stop_loss = zone_low - atr
    take_profit = zone_high + (atr * 2)

    result = validate_trade_levels(
        direction=SignalDirection.LONG,
        entry_price=entry_price,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr=atr,
    )
    assert result.valid is True


def test_buy_invalid_sl_above_zone_low() -> None:
    zone_low, zone_high = 100.0, 110.0
    result = validate_trade_levels(
        direction=SignalDirection.LONG,
        entry_price=105.0,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        stop_loss=101.0,
        take_profit=130.0,
        atr=5.0,
    )
    assert result.valid is False
    assert result.reason == "invalid_trade_levels"
    assert result.detail == "buy_sl_not_below_zone_low"


def test_buy_invalid_sl_distance() -> None:
    zone_low, zone_high = 100.0, 110.0
    entry_price = 100.5
    atr = 5.0
    stop_loss = 99.0
    take_profit = 130.0
    result = validate_trade_levels(
        direction=SignalDirection.LONG,
        entry_price=entry_price,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr=atr,
    )
    assert result.valid is False
    assert result.detail == "sl_distance_below_atr"


def test_sell_valid_trade_levels() -> None:
    zone_low, zone_high = 100.0, 110.0
    entry_price = 105.0
    atr = 5.0
    stop_loss = zone_high + atr
    take_profit = zone_low - (atr * 2)

    result = validate_trade_levels(
        direction=SignalDirection.SHORT,
        entry_price=entry_price,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr=atr,
    )
    assert result.valid is True


def test_sell_invalid_tp_above_zone_low() -> None:
    zone_low, zone_high = 100.0, 110.0
    result = validate_trade_levels(
        direction=SignalDirection.SHORT,
        entry_price=105.0,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        stop_loss=115.0,
        take_profit=101.0,
        atr=5.0,
    )
    assert result.valid is False
    assert result.reason == "invalid_trade_levels"
    assert result.detail == "sell_tp_not_below_zone_low"


def test_sell_invalid_risk_reward() -> None:
    zone_low, zone_high = 100.0, 110.0
    result = validate_trade_levels(
        direction=SignalDirection.SHORT,
        entry_price=105.0,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        stop_loss=115.0,
        take_profit=94.0,
        atr=5.0,
        min_rr=2.0,
    )
    assert result.valid is False
    assert result.detail == "risk_reward_below_2.0"
