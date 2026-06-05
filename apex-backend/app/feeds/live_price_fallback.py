"""Free live price fallbacks when TwelveData is unavailable.

Finnhub forex OHLC requires a paid plan (403 on free tier). These sources work on
free tiers and provide immediate live bars for the resolver chain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config.assets import AssetConfig
from app.feeds.alphavantage_client import fetch_fx_intraday_bars
from app.feeds.finnhub_market import fetch_finnhub_latest_bar
from app.feeds.frankfurter_client import build_hourly_bar, fetch_latest_rate_with_source
from app.logging_config import logger

METALS_LIVE_GOLD_URL = "https://api.metals.live/v1/spot/gold"


async def fetch_fx_live_bar(asset: AssetConfig) -> tuple[dict[str, Any] | None, str | None]:
    if not asset.frankfurter_from_symbol or not asset.frankfurter_to_symbol:
        return None, None
    try:
        rate, source = await fetch_latest_rate_with_source(
            asset.frankfurter_from_symbol,
            asset.frankfurter_to_symbol,
        )
    except Exception as exc:
        logger.warning("fx_live_fetch_failed", symbol=asset.symbol, error=str(exc))
        return None, None
    if rate is None or not source:
        return None, None
    bar = build_hourly_bar(apex_symbol=asset.symbol, price=rate, source=source)
    logger.info("fx_live_bar", symbol=asset.symbol, source=source, price=rate)
    return bar, source


async def fetch_frankfurter_live_bar(asset: AssetConfig) -> dict[str, Any] | None:
    bar, _ = await fetch_fx_live_bar(asset)
    return bar


async def fetch_alphavantage_live_bar(asset: AssetConfig) -> dict[str, Any] | None:
    if not asset.alphavantage_from_symbol or not asset.alphavantage_to_symbol:
        return None
    try:
        bars = await fetch_fx_intraday_bars(
            from_symbol=asset.alphavantage_from_symbol,
            to_symbol=asset.alphavantage_to_symbol,
            apex_symbol=asset.symbol,
            interval=asset.candle_interval,
            outputsize="compact",
        )
    except Exception as exc:
        logger.warning("alphavantage_live_fetch_failed", symbol=asset.symbol, error=str(exc))
        return None
    if not bars:
        return None
    bar = bars[-1]
    logger.info("alphavantage_live_bar", symbol=asset.symbol, close=bar["close"])
    return bar


async def fetch_metals_live_gold_bar(apex_symbol: str = "XAUUSD") -> dict[str, Any] | None:
    """Free spot gold fallback for XAUUSD when FX APIs do not cover metals."""
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(METALS_LIVE_GOLD_URL)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("metals_live_fetch_failed", symbol=apex_symbol, error=str(exc))
        return None

    price: float | None = None
    if isinstance(payload, list) and payload:
        row = payload[0]
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            price = float(row[1])
        elif isinstance(row, dict):
            price = float(row.get("price") or row.get("spot") or 0)
    elif isinstance(payload, dict):
        price = float(payload.get("price") or payload.get("spot") or 0)

    if not price:
        return None

    bar = build_hourly_bar(apex_symbol=apex_symbol, price=price)
    bar["source"] = "metals_live"
    logger.info("metals_live_bar", symbol=apex_symbol, price=price)
    return bar


async def fetch_finnhub_live_bar(asset: AssetConfig) -> dict[str, Any] | None:
    if not asset.finnhub_symbol:
        return None
    bar = await fetch_finnhub_latest_bar(
        asset.symbol,
        asset.finnhub_symbol,
        interval=asset.candle_interval,
    )
    if bar:
        logger.info("finnhub_live_bar", symbol=asset.symbol)
    return bar


async def fetch_live_fallback_bar(asset: AssetConfig) -> tuple[dict[str, Any] | None, str | None]:
    """Try free fallbacks first, then Finnhub (premium), in priority order."""
    if asset.frankfurter_from_symbol and asset.frankfurter_to_symbol:
        bar, source = await fetch_fx_live_bar(asset)
        if bar and source:
            return bar, source

    if asset.alphavantage_from_symbol and asset.alphavantage_to_symbol:
        bar = await fetch_alphavantage_live_bar(asset)
        if bar:
            return bar, "alphavantage"

    if asset.symbol == "XAUUSD":
        bar = await fetch_metals_live_gold_bar(asset.symbol)
        if bar:
            return bar, "metals_live"

    bar = await fetch_finnhub_live_bar(asset)
    if bar:
        return bar, "finnhub"

    return None, None
