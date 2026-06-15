"""Price zone helpers — ±0.25% bands for SNR levels and entry regions."""

from __future__ import annotations

ZONE_LOW_MULTIPLIER = 0.9975
ZONE_HIGH_MULTIPLIER = 1.0025


def level_zone_bounds(level: float, *, decimals: int = 5) -> tuple[float, float]:
    """Return (low, high) for a single SNR level zone."""
    low = round(level * ZONE_LOW_MULTIPLIER, decimals)
    high = round(level * ZONE_HIGH_MULTIPLIER, decimals)
    return low, high


def entry_zone_from_price(price: float, *, decimals: int = 2) -> tuple[float, float, float]:
    """Return (zone_low, zone_high, center) from current price."""
    zone_low, zone_high = level_zone_bounds(price, decimals=decimals)
    center = round((zone_low + zone_high) / 2, decimals)
    return zone_low, zone_high, center


def price_in_zone(price: float, zone_low: float, zone_high: float) -> bool:
    return zone_low <= price <= zone_high


def price_in_level_zone(price: float, level: float, *, decimals: int = 5) -> bool:
    """True when price lies within ±0.25% band around a single SNR level."""
    if level <= 0:
        return False
    low, high = level_zone_bounds(level, decimals=decimals)
    return price_in_zone(price, low, high)
