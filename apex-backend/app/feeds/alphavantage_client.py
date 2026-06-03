"""Alpha Vantage FX API client — shared by live feed and bootstrap."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.logging_config import logger

BASE_URL = "https://www.alphavantage.co/query"

INTERVAL_MAP: dict[str, str] = {
    "1h": "60min",
    "30min": "30min",
    "15min": "15min",
    "5min": "5min",
    "1min": "1min",
}


def _parse_av_timestamp(raw: str) -> datetime:
    # Alpha Vantage FX intraday: "2024-01-15 19:00"
    ts = datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S")
    return ts.replace(tzinfo=timezone.utc)


def _series_key(interval: str) -> str:
    av_interval = INTERVAL_MAP.get(interval, interval)
    return f"Time Series FX ({av_interval})"


def parse_fx_intraday_payload(
    data: dict[str, Any],
    *,
    apex_symbol: str,
    interval: str = "1h",
) -> list[dict[str, Any]]:
    if data.get("Error Message"):
        raise RuntimeError(str(data["Error Message"]))
    if data.get("Information"):
        raise RuntimeError(str(data["Information"]))
    if data.get("Note"):
        raise RuntimeError(str(data["Note"]))

    series = data.get(_series_key(interval))
    if not series:
        return []

    bars: list[dict[str, Any]] = []
    for ts_raw, row in series.items():
        ts = _parse_av_timestamp(ts_raw)
        bars.append(
            {
                "symbol": apex_symbol,
                "timestamp": ts.isoformat(),
                "open": float(row["1. open"]),
                "high": float(row["2. high"]),
                "low": float(row["3. low"]),
                "close": float(row["4. close"]),
                "volume": 0.0,
                "source": "alphavantage",
                "is_closed": True,
            }
        )
    bars.sort(key=lambda b: b["timestamp"])
    return bars


async def fetch_fx_intraday_bars(
    *,
    from_symbol: str,
    to_symbol: str,
    apex_symbol: str,
    interval: str = "1h",
    outputsize: str = "full",
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    key = api_key or settings.alphavantage_api_key
    if not key or key == "your_key_here":
        logger.warning("alphavantage_api_key_not_configured", symbol=apex_symbol)
        return []

    av_interval = INTERVAL_MAP.get(interval, interval)
    params = {
        "function": "FX_INTRADAY",
        "from_symbol": from_symbol,
        "to_symbol": to_symbol,
        "interval": av_interval,
        "outputsize": outputsize,
        "apikey": key,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        from app.feeds.alphavantage_limiter import throttled_get

        response = await throttled_get(client, BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

    bars = parse_fx_intraday_payload(data, apex_symbol=apex_symbol, interval=interval)
    if not bars:
        logger.warning("alphavantage_no_data", symbol=apex_symbol, keys=list(data.keys())[:5])
    return bars
