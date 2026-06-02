"""Fetch historical OHLCV bars to warm the pipeline buffer on startup."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.config.assets import ASSETS, AssetConfig
from app.logging_config import logger


def _normalize_bar(
    symbol: str,
    timestamp: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    source: str,
) -> dict[str, Any]:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return {
        "symbol": symbol,
        "timestamp": timestamp.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "source": source,
        "is_closed": True,
    }


async def fetch_binance_history(
    symbol: str, limit: int = 100, interval: str = "1h"
) -> list[dict[str, Any]]:
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        rows = response.json()

    bars: list[dict[str, Any]] = []
    for row in rows:
        ts = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
        bars.append(
            _normalize_bar(
                symbol=symbol,
                timestamp=ts,
                open_=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                source="binance",
            )
        )
    return bars


async def fetch_twelvedata_history(
    td_symbol: str,
    apex_symbol: str,
    limit: int = 100,
    interval: str = "1h",
) -> list[dict[str, Any]]:
    api_key = settings.twelvedata_api_key
    if not api_key or api_key == "your_key_here":
        logger.warning("twelvedata_bootstrap_skipped", reason="api_key_missing")
        return []

    params = {
        "symbol": td_symbol,
        "interval": interval,
        "outputsize": limit,
        "apikey": api_key,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        from app.feeds.twelvedata_limiter import throttled_get

        response = await throttled_get(
            client,
            "https://api.twelvedata.com/time_series",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

    if "values" not in data or not data["values"]:
        logger.warning("twelvedata_bootstrap_no_data", response=data)
        return []

    bars: list[dict[str, Any]] = []
    for row in reversed(data["values"]):
        ts = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        bars.append(
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
    return bars


async def fetch_history_for_asset(asset: AssetConfig, limit: int = 100) -> list[dict[str, Any]]:
    if asset.feed_type == "binance":
        return await fetch_binance_history(asset.symbol, limit, asset.candle_interval)
    if asset.feed_type == "twelvedata" and asset.twelvedata_symbol:
        return await fetch_twelvedata_history(
            asset.twelvedata_symbol,
            asset.symbol,
            limit,
            asset.candle_interval,
        )
    return []


async def bootstrap_asset(symbol: str, limit: int = 250) -> bool:
    """Fetch H1 history and warm pipeline for one symbol. Returns True on success."""
    from app.services.market_hours import is_market_open
    from app.services.pipeline import process_bar, seed_bars_to_buffer

    asset = ASSETS.get(symbol)
    if asset is None:
        return False
    if not is_market_open(symbol):
        logger.info("history_bootstrap_skipped_closed", symbol=symbol)
        return False
    try:
        bars = await fetch_history_for_asset(asset, limit)
        if not bars:
            logger.warning("history_bootstrap_empty", symbol=symbol)
            return False
        seed_bars_to_buffer(bars)
        await process_bar(bars[-1])
        logger.info("history_bootstrap_complete", symbol=symbol, bars=len(bars))
        return True
    except Exception as exc:
        logger.error("history_bootstrap_failed", symbol=symbol, error=str(exc))
        return False


async def bootstrap_all_assets(limit: int = 250) -> None:
    for symbol, asset in ASSETS.items():
        await bootstrap_asset(symbol, limit)
        if asset.feed_type == "twelvedata":
            await asyncio.sleep(4)
