"""Price zone helpers."""

from app.utils.price_zones import entry_zone_from_price, level_zone_bounds, price_in_level_zone, price_in_zone


def test_level_zone_bounds_025_percent() -> None:
    low, high = level_zone_bounds(100.0, decimals=2)
    assert low == 99.75
    assert high == 100.25


def test_entry_zone_from_price() -> None:
    low, high, center = entry_zone_from_price(2700.0, decimals=2)
    assert low == 2693.25
    assert high == 2706.75
    assert center == 2700.0
    assert price_in_zone(2700.0, low, high)


def test_s1_zone_formula() -> None:
    low, high = level_zone_bounds(4313.87, decimals=2)
    assert low == round(4313.87 * 0.9975, 2)
    assert high == round(4313.87 * 1.0025, 2)


def test_price_in_level_zone_xauusd_levels() -> None:
    assert price_in_level_zone(4311.0, 4332.0) is False
    assert price_in_level_zone(4311.0, 4186.0) is False
    assert price_in_level_zone(4332.0, 4332.0) is True
