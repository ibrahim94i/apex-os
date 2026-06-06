"""Volume reliability policy — XAUUSD spot gold has no meaningful volume from TwelveData."""

from __future__ import annotations

from typing import Any

from app.config.assets import ASSETS


def volume_is_reliable(symbol: str) -> bool:
    asset = ASSETS.get(symbol)
    if asset is None:
        return True
    return asset.volume_reliable


def apply_volume_policy(symbol: str, volume: float) -> float:
    """Return 0 for symbols where volume data is unavailable/unreliable."""
    if not volume_is_reliable(symbol):
        return 0.0
    return volume


def apply_volume_policy_to_bar(bar: dict[str, Any]) -> dict[str, Any]:
    symbol = bar.get("symbol", "")
    if volume_is_reliable(symbol):
        return bar
    out = dict(bar)
    out["volume"] = 0.0
    return out
