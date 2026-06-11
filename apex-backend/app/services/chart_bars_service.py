"""Chart-only OHLCV bars — does not affect agent pipeline (agents stay on H1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from app.config import settings
from app.config.assets import get_asset
from app.feeds.history_bootstrap import _finalize_bar, _normalize_bar
from app.feeds.twelvedata_limiter import can_afford_credits, throttled_get
from app.logging_config import logger
from app.services.market_data_store import fetch_bars_from_db

ChartTimeframe = Literal["M5", "M15", "H1", "H4", "D1"]

CHART_TIMEFRAMES: dict[str, str] = {
    "M5": "5min",
    "M15": "15min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}

DEFAULT_CHART_TIMEFRAME: ChartTimeframe = "H1"
AGENT_TIMEFRAME = "H1"

TWELVEDATA_URL = "https://api.twelvedata.com/time_series"


def normalize_chart_timeframe(value: str) -> ChartTimeframe:
    code = value.strip().upper()
    if code not in CHART_TIMEFRAMES:
        raise ValueError(f"Unsupported chart timeframe: {value}")
    return code  # type: ignore[return-value]


async def _fetch_twelvedata_chart_series(
    *,
    td_symbol: str,
    apex_symbol: str,
    interval: str,
    limit: int,
) -> list[dict[str, Any]]:
    api_key = settings.twelvedata_api_key
    if not api_key or api_key == "your_key_here":
        return []

    if not await can_afford_credits(limit):
        logger.warning("chart_bars_skipped_credits", symbol=apex_symbol, interval=interval)
        return []

    params = {
        "symbol": td_symbol,
        "interval": interval,
        "outputsize": limit,
        "apikey": api_key,
    }

    data: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(1, 4):
            response = await throttled_get(
                client,
                TWELVEDATA_URL,
                params=params,
                reason="chart_view",
            )
            if response.status_code == 429:
                await asyncio.sleep(15.0 * attempt)
                continue
            if response.status_code == 404:
                logger.warning(
                    "chart_bars_interval_unavailable",
                    symbol=apex_symbol,
                    interval=interval,
                )
                return []
            response.raise_for_status()
            data = response.json()
            break

    if not data or "values" not in data or not data["values"]:
        return []

    bars: list[dict[str, Any]] = []
    for row in reversed(data["values"]):
        ts = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        bars.append(
            _finalize_bar(
                _normalize_bar(
                    symbol=apex_symbol,
                    timestamp=ts,
                    open_=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                    source="twelvedata",
                )
            )
        )
    return bars


async def fetch_chart_bars(
    symbol: str,
    *,
    interval: str = DEFAULT_CHART_TIMEFRAME,
    limit: int = 200,
) -> tuple[list[dict[str, Any]], ChartTimeframe]:
    """Return bars for dashboard chart display only."""
    timeframe = normalize_chart_timeframe(interval)
    capped_limit = min(max(limit, 1), 500)

    if timeframe == "H1":
        return await fetch_bars_from_db(symbol, capped_limit), timeframe

    asset = get_asset(symbol)
    if asset and asset.feed_type == "twelvedata" and asset.twelvedata_symbol:
        bars = await _fetch_twelvedata_chart_series(
            td_symbol=asset.twelvedata_symbol,
            apex_symbol=symbol,
            interval=CHART_TIMEFRAMES[timeframe],
            limit=capped_limit,
        )
        if bars:
            return bars, timeframe
        logger.warning(
            "chart_bars_fallback_h1_db",
            symbol=symbol,
            requested=timeframe,
        )

    return await fetch_bars_from_db(symbol, capped_limit), "H1"
