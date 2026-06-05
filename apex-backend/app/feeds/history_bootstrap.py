"""Fetch historical OHLCV bars to warm the pipeline buffer on startup."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.config.assets import ACTIVE_SYMBOLS, ASSETS, AssetConfig
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
    data: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        from app.feeds.twelvedata_limiter import throttled_get

        for attempt in range(1, 5):
            response = await throttled_get(
                client,
                "https://api.twelvedata.com/time_series",
                params=params,
            )
            if response.status_code == 404:
                logger.warning(
                    "twelvedata_symbol_unavailable",
                    symbol=apex_symbol,
                    td_symbol=td_symbol,
                    hint="symbol may require a paid TwelveData plan",
                )
                return []
            if response.status_code == 429:
                body: dict[str, Any] = {}
                try:
                    body = response.json()
                except Exception:
                    pass
                if "run out of api credits" in str(body.get("message", "")).lower():
                    logger.warning("twelvedata_credits_exhausted", symbol=apex_symbol)
                    return []
                wait = 30.0 * attempt
                logger.warning(
                    "twelvedata_bootstrap_rate_limited",
                    symbol=apex_symbol,
                    attempt=attempt,
                    wait_seconds=wait,
                )
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            break

    if data is None:
        logger.error("twelvedata_bootstrap_rate_limited_exhausted", symbol=apex_symbol)
        return []

    if "values" not in data or not data["values"]:
        logger.warning("twelvedata_bootstrap_no_data", symbol=apex_symbol, response=data)
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


async def fetch_alphavantage_history(
    asset: AssetConfig,
    limit: int = 250,
) -> list[dict[str, Any]]:
    if not asset.alphavantage_from_symbol or not asset.alphavantage_to_symbol:
        return []

    from app.feeds.alphavantage_client import fetch_fx_intraday_bars

    bars = await fetch_fx_intraday_bars(
        from_symbol=asset.alphavantage_from_symbol,
        to_symbol=asset.alphavantage_to_symbol,
        apex_symbol=asset.symbol,
        interval=asset.candle_interval,
        outputsize="full",
    )
    if len(bars) < limit:
        from app.services.market_data_store import fetch_bars_from_db

        db_bars = await fetch_bars_from_db(asset.symbol, limit)
        seen = {b["timestamp"] for b in bars}
        merged = list(bars)
        for bar in db_bars:
            if bar["timestamp"] not in seen:
                merged.append(bar)
        merged.sort(key=lambda b: b["timestamp"])
        bars = merged[-limit:]
    return bars


async def fetch_frankfurter_history(
    asset: AssetConfig,
    limit: int = 250,
) -> list[dict[str, Any]]:
    if not asset.frankfurter_from_symbol or not asset.frankfurter_to_symbol:
        return []

    from app.feeds.frankfurter_client import fetch_historical_daily_bars
    from app.services.market_data_store import fetch_bars_from_db

    db_bars = await fetch_bars_from_db(asset.symbol, limit)
    if len(db_bars) >= limit:
        return db_bars[-limit:]

    daily = await fetch_historical_daily_bars(
        from_symbol=asset.frankfurter_from_symbol,
        to_symbol=asset.frankfurter_to_symbol,
        apex_symbol=asset.symbol,
        days=min(365, limit + 30),
    )
    seen = {b["timestamp"] for b in db_bars}
    merged = list(db_bars)
    for bar in daily:
        if bar["timestamp"] not in seen:
            merged.append(bar)
    merged.sort(key=lambda b: b["timestamp"])
    return merged[-limit:] if merged else []


async def fetch_bootstrap_history(asset: AssetConfig, limit: int = 250) -> list[dict[str, Any]]:
    """Bootstrap: TwelveData (gold) or Frankfurter (FX) → DB fallback."""
    bars = await fetch_history_for_asset(asset, limit)
    if len(bars) >= limit:
        logger.info(
            "history_bootstrap_primary",
            symbol=asset.symbol,
            source=asset.feed_type,
            bars=len(bars),
        )
        return bars[-limit:]
    if bars:
        logger.info(
            "history_bootstrap_partial",
            symbol=asset.symbol,
            source=asset.feed_type,
            bars=len(bars),
        )
        return bars

    from app.services.market_data_store import fetch_bars_from_db

    db_bars = await fetch_bars_from_db(asset.symbol, limit)
    if db_bars:
        logger.info("history_bootstrap_db_fallback", symbol=asset.symbol, bars=len(db_bars))
    return db_bars


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
    if asset.feed_type == "alphavantage":
        return await fetch_alphavantage_history(asset, limit)
    if asset.feed_type == "frankfurter":
        return await fetch_frankfurter_history(asset, limit)
    return []


async def _mark_feed_warmed(symbol: str, bar: dict[str, Any]) -> None:
    from app.core.cache import set_feed_last_update, set_latest_price

    await set_latest_price(symbol, bar["close"], bar["timestamp"])
    await set_feed_last_update(symbol, bar["timestamp"])


async def refresh_dashboard_cache() -> None:
    from app.core.cache import set_dashboard_state
    from app.services.dashboard_builder import build_asset_dashboard_state

    for symbol in ACTIVE_SYMBOLS:
        dashboard = await build_asset_dashboard_state(symbol)
        await set_dashboard_state(symbol, dashboard.model_dump(mode="json"))


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
        bars = await fetch_bootstrap_history(asset, limit)
        if not bars:
            logger.warning("history_bootstrap_empty", symbol=symbol)
            return False
        seed_bars_to_buffer(bars)
        last_bar = bars[-1]
        await process_bar(last_bar, skip_agents=True)
        await _mark_feed_warmed(symbol, last_bar)
        logger.info("history_bootstrap_complete", symbol=symbol, bars=len(bars))
        return True
    except Exception as exc:
        logger.error("history_bootstrap_failed", symbol=symbol, error=str(exc))
        return False


async def bootstrap_all_assets(limit: int = 250) -> None:
    failed: list[str] = []

    for symbol in ACTIVE_SYMBOLS:
        ok = await bootstrap_asset(symbol, limit)
        if not ok:
            failed.append(symbol)
        await asyncio.sleep(1)

    for attempt in range(1, 4):
        if not failed:
            break
        logger.warning("history_bootstrap_retry_batch", symbols=failed, attempt=attempt)
        await asyncio.sleep(45 * attempt)
        still_failed: list[str] = []
        for symbol in failed:
            asset = ASSETS[symbol]
            ok = await bootstrap_asset(symbol, limit)
            if ok:
                continue
            from app.services.market_data_store import fetch_bars_from_db

            db_bars = await fetch_bars_from_db(symbol, limit)
            if len(db_bars) >= 200:
                from app.services.pipeline import process_bar, seed_bars_to_buffer

                seed_bars_to_buffer(db_bars)
                last_bar = db_bars[-1]
                await process_bar(last_bar, skip_agents=True)
                await _mark_feed_warmed(symbol, last_bar)
                logger.info("history_bootstrap_db_retry_success", symbol=symbol, bars=len(db_bars))
                continue
            if db_bars:
                logger.warning(
                    "history_bootstrap_db_insufficient_bars",
                    symbol=symbol,
                    bars=len(db_bars),
                    required=200,
                )
            still_failed.append(symbol)
            await asyncio.sleep(1)
        failed = still_failed

    if failed:
        logger.error("history_bootstrap_symbols_failed", symbols=failed)
    await refresh_dashboard_cache()
    from app.services.agent_analysis_service import ensure_agent_consensus_for_active_symbols

    await ensure_agent_consensus_for_active_symbols()
