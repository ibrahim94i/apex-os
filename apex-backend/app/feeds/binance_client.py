"""Binance public REST klines client — no API key required."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.logging_config import logger

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def kline_row_to_bar(symbol: str, row: list[Any]) -> dict[str, Any]:
    ts = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
    close_time = datetime.fromtimestamp(row[6] / 1000, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    return {
        "symbol": symbol,
        "timestamp": ts.isoformat(),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
        "source": "binance",
        "is_closed": close_time <= now,
    }


async def fetch_binance_klines(
    symbol: str,
    *,
    limit: int = 100,
    interval: str = "1h",
) -> list[dict[str, Any]]:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(BINANCE_KLINES_URL, params=params)
        response.raise_for_status()
        rows = response.json()
    return [kline_row_to_bar(symbol, row) for row in rows]


async def fetch_binance_latest_bar(
    symbol: str,
    *,
    interval: str = "1h",
) -> dict[str, Any] | None:
    try:
        bars = await fetch_binance_klines(symbol, limit=2, interval=interval)
    except Exception as exc:
        logger.warning("binance_klines_fetch_failed", symbol=symbol, error=str(exc))
        return None
    return bars[-1] if bars else None
