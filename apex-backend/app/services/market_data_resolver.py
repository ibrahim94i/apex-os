"""Live market data resolution — Binance primary for gold, TwelveData fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from app.config import settings
from app.config.assets import BinanceMarket, get_asset
from app.feeds.binance_client import fetch_binance_latest_bar
from app.feeds.twelvedata_limiter import throttled_get
from app.logging_config import logger
from app.services.data_source_monitor import report_live_bar_source
from app.services.market_data_store import fetch_bars_from_db

LiveDataSource = Literal["binance", "twelvedata", "db"]
PRIMARY_LIVE_SOURCE: LiveDataSource = "binance"
FALLBACK_LIVE_SOURCE: LiveDataSource = "twelvedata"
LAST_RESORT_LIVE_SOURCE: LiveDataSource = "db"

TWELVEDATA_URL = "https://api.twelvedata.com/time_series"


async def _fetch_binance_latest(
    apex_symbol: str,
    binance_symbol: str,
    interval: str,
    market: BinanceMarket,
) -> dict[str, Any] | None:
    bar = await fetch_binance_latest_bar(
        binance_symbol,
        interval=interval,
        market=market,
        apex_symbol=apex_symbol,
    )
    if not bar:
        return None
    from app.utils.volume_policy import apply_volume_policy_to_bar

    return apply_volume_policy_to_bar(bar)


async def _fetch_twelvedata_latest(
    apex_symbol: str,
    td_symbol: str,
    interval: str,
) -> dict[str, Any] | None:
    if not settings.twelvedata_api_key or settings.twelvedata_api_key == "your_key_here":
        return None

    from app.feeds.twelvedata_limiter import should_skip_twelvedata_api

    if await should_skip_twelvedata_api(1):
        return None

    params = {
        "symbol": td_symbol,
        "interval": interval,
        "outputsize": 1,
        "apikey": settings.twelvedata_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await throttled_get(client, TWELVEDATA_URL, params=params, reason="live_poll")
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
    from app.utils.volume_policy import apply_volume_policy_to_bar

    return apply_volume_policy_to_bar(
        {
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
    )


async def _fetch_db_latest(apex_symbol: str) -> dict[str, Any] | None:
    bars = await fetch_bars_from_db(apex_symbol, limit=1)
    if not bars:
        return None
    bar = dict(bars[-1])
    bar["source"] = bar.get("source") or "db"
    return bar


async def fetch_twelvedata_live_close(symbol: str) -> float | None:
    """Latest close from live feeds — Binance first for gold, else TwelveData."""
    asset = get_asset(symbol)
    if asset and asset.feed_type == "binance":
        binance_symbol = asset.binance_symbol or asset.symbol
        bar = await _fetch_binance_latest(
            symbol,
            binance_symbol,
            asset.candle_interval,
            asset.binance_market,
        )
        if bar:
            return float(bar["close"])
        if asset.twelvedata_symbol:
            bar = await _fetch_twelvedata_latest(symbol, asset.twelvedata_symbol, asset.candle_interval)
            if bar:
                return float(bar["close"])
        return None

    if not asset or asset.feed_type != "twelvedata" or not asset.twelvedata_symbol:
        return None
    bar = await _fetch_twelvedata_latest(
        symbol,
        asset.twelvedata_symbol,
        asset.candle_interval,
    )
    if not bar:
        return None
    return float(bar["close"])


async def fetch_live_bar_with_fallback(
    apex_symbol: str,
    td_symbol: str | None = None,
    *,
    interval: str = "1h",
) -> tuple[dict[str, Any] | None, LiveDataSource | None]:
    """Resolve latest bar: Binance (XAUUSD) → TwelveData → DB."""
    asset = get_asset(apex_symbol)

    if asset and asset.feed_type == "binance":
        binance_symbol = asset.binance_symbol or asset.symbol
        bar = await _fetch_binance_latest(
            apex_symbol,
            binance_symbol,
            interval,
            asset.binance_market,
        )
        if bar:
            await report_live_bar_source(apex_symbol, PRIMARY_LIVE_SOURCE)
            return bar, PRIMARY_LIVE_SOURCE

    td = td_symbol or (asset.twelvedata_symbol if asset else None)
    if td:
        bar = await _fetch_twelvedata_latest(apex_symbol, td, interval)
        if bar:
            await report_live_bar_source(apex_symbol, FALLBACK_LIVE_SOURCE)
            logger.info("live_bar_twelvedata_fallback", symbol=apex_symbol)
            return bar, FALLBACK_LIVE_SOURCE

    bar = await _fetch_db_latest(apex_symbol)
    if bar:
        logger.info("live_bar_db_fallback", symbol=apex_symbol)
        return bar, LAST_RESORT_LIVE_SOURCE

    logger.error("live_bar_all_sources_failed", symbol=apex_symbol)
    return None, None
