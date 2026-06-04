"""Frankfurter API — free EUR/USD rates, no API key required."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.logging_config import logger

BASE_URL = "https://api.frankfurter.app"


async def fetch_latest_rate(from_symbol: str, to_symbol: str) -> float | None:
    params = {"from": from_symbol, "to": to_symbol}
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{BASE_URL}/latest", params=params)
        response.raise_for_status()
        data = response.json()
    rates = data.get("rates") or {}
    rate = rates.get(to_symbol)
    return float(rate) if rate is not None else None


async def fetch_historical_daily_bars(
    *,
    from_symbol: str,
    to_symbol: str,
    apex_symbol: str,
    days: int = 365,
) -> list[dict[str, Any]]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    url = f"{BASE_URL}/{start.isoformat()}..{end.isoformat()}"
    params = {"from": from_symbol, "to": to_symbol}

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    rates: dict[str, float] = data.get("rates") or {}
    bars: list[dict[str, Any]] = []
    for day_str, rate_map in sorted(rates.items()):
        rate = rate_map.get(to_symbol)
        if rate is None:
            continue
        price = float(rate)
        ts = datetime.strptime(day_str, "%Y-%m-%d").replace(
            hour=12, minute=0, second=0, tzinfo=timezone.utc
        )
        bars.append(
            {
                "symbol": apex_symbol,
                "timestamp": ts.isoformat(),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0.0,
                "source": "frankfurter",
                "is_closed": True,
            }
        )
    if not bars:
        logger.warning("frankfurter_no_history", symbol=apex_symbol)
    return bars


def build_hourly_bar(
    *,
    apex_symbol: str,
    price: float,
    at: datetime | None = None,
) -> dict[str, Any]:
    now = at or datetime.now(timezone.utc)
    ts = now.replace(minute=0, second=0, microsecond=0)
    return {
        "symbol": apex_symbol,
        "timestamp": ts.isoformat(),
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": 0.0,
        "source": "frankfurter",
        "is_closed": False,
    }
