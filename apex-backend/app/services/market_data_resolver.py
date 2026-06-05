"""Live market data resolution — strict source priority.

1. TwelveData (primary) — every poll (5 min)
2. Free fallbacks when TwelveData fails (429/credits): Frankfurter → Alpha Vantage → metals.live (XAU)
3. Finnhub (premium forex OHLC — skipped on free tier 403)
4. DB (last resort)

Auto-return to TwelveData when the next poll succeeds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, cast

import httpx

from app.config import settings
from app.config.assets import get_asset
from app.feeds.live_price_fallback import fetch_live_fallback_bar
from app.feeds.twelvedata_limiter import throttled_get
from app.logging_config import logger
from app.services.data_source_monitor import report_live_bar_source
from app.services.market_data_store import fetch_bars_from_db

LiveDataSource = Literal["twelvedata", "frankfurter", "alphavantage", "metals_live", "finnhub", "db"]
PRIMARY_LIVE_SOURCE: LiveDataSource = "twelvedata"
FALLBACK_LIVE_SOURCES = ("frankfurter", "alphavantage", "metals_live", "finnhub")
LAST_RESORT_LIVE_SOURCE: LiveDataSource = "db"

TWELVEDATA_URL = "https://api.twelvedata.com/time_series"


async def _fetch_twelvedata_latest(
    apex_symbol: str,
    td_symbol: str,
    interval: str,
) -> dict[str, Any] | None:
    if not settings.twelvedata_api_key or settings.twelvedata_api_key == "your_key_here":
        return None

    params = {
        "symbol": td_symbol,
        "interval": interval,
        "outputsize": 1,
        "apikey": settings.twelvedata_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await throttled_get(client, TWELVEDATA_URL, params=params)
            if response.status_code in (404, 429):
                logger.warning(
                    "twelvedata_live_fetch_skipped",
                    symbol=apex_symbol,
                    status=response.status_code,
                )
                return None
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (404, 429):
            logger.warning(
                "twelvedata_live_fetch_skipped",
                symbol=apex_symbol,
                status=exc.response.status_code,
            )
            return None
        raise
    except Exception as exc:
        logger.warning("twelvedata_live_fetch_failed", symbol=apex_symbol, error=str(exc))
        return None

    if data.get("status") == "error":
        logger.warning(
            "twelvedata_live_api_error",
            symbol=apex_symbol,
            message=data.get("message"),
        )
        return None
    if "values" not in data or not data["values"]:
        return None

    row = data["values"][0]
    ts = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return {
        "symbol": apex_symbol,
        "timestamp": ts.isoformat(),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row.get("volume", 0)),
        "source": "twelvedata",
        "is_closed": True,
    }


async def _fetch_db_latest(apex_symbol: str) -> dict[str, Any] | None:
    bars = await fetch_bars_from_db(apex_symbol, limit=1)
    if not bars:
        return None
    bar = dict(bars[-1])
    bar["source"] = bar.get("source") or "db"
    return bar


async def fetch_live_bar_with_fallback(
    apex_symbol: str,
    td_symbol: str,
    *,
    interval: str = "1h",
) -> tuple[dict[str, Any] | None, LiveDataSource | None]:
    """Resolve latest bar: TwelveData → free fallbacks → DB."""
    asset = get_asset(apex_symbol)

    # 1. Primary — always try TwelveData first (even after a prior 429)
    bar = await _fetch_twelvedata_latest(apex_symbol, td_symbol, interval)
    if bar:
        await report_live_bar_source(apex_symbol, PRIMARY_LIVE_SOURCE)
        return bar, PRIMARY_LIVE_SOURCE

    # 2. Fallback — Frankfurter → Alpha Vantage → metals (XAU) → Finnhub (premium)
    if asset:
        bar, fallback_source = await fetch_live_fallback_bar(asset)
        if bar and fallback_source:
            await report_live_bar_source(apex_symbol, fallback_source)
            logger.info("live_bar_fallback_active", symbol=apex_symbol, source=fallback_source)
            return bar, cast(LiveDataSource, fallback_source)

    # 3. Last resort — cached DB bar
    bar = await _fetch_db_latest(apex_symbol)
    if bar:
        await report_live_bar_source(apex_symbol, LAST_RESORT_LIVE_SOURCE)
        logger.info("live_bar_db_fallback", symbol=apex_symbol)
        return bar, LAST_RESORT_LIVE_SOURCE

    logger.error("live_bar_all_sources_failed", symbol=apex_symbol)
    return None, None
