"""Fetch historical OHLCV bars to warm the pipeline buffer on startup."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.config.assets import ACTIVE_SYMBOLS, ASSETS, AssetConfig
from app.logging_config import logger

BINANCE_BOOTSTRAP_BARS = 200
DEFAULT_BOOTSTRAP_BARS = 250
XAUUSD_BOOTSTRAP_BARS = 500


def bootstrap_limit_for(asset: AssetConfig) -> int:
    if asset.symbol == "XAUUSD":
        return XAUUSD_BOOTSTRAP_BARS
    if asset.feed_type == "binance":
        return BINANCE_BOOTSTRAP_BARS
    return DEFAULT_BOOTSTRAP_BARS


def bootstrap_success_threshold(asset: AssetConfig, bar_limit: int) -> int:
    """Minimum bars required to treat bootstrap as successful."""
    if asset.symbol == "XAUUSD":
        return min(bar_limit, 200)
    if asset.feed_type == "binance":
        return min(bar_limit, BINANCE_BOOTSTRAP_BARS)
    return min(bar_limit, 50)


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
    close_time = timestamp + timedelta(hours=1)
    return {
        "symbol": symbol,
        "timestamp": timestamp.isoformat(),
        "close_time": close_time.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "source": source,
        "is_closed": True,
    }


def _finalize_bar(bar: dict[str, Any]) -> dict[str, Any]:
    from app.utils.volume_policy import apply_volume_policy_to_bar

    return apply_volume_policy_to_bar(bar)


async def fetch_binance_history(
    symbol: str,
    limit: int = 100,
    interval: str = "1h",
    *,
    market: str = "spot",
    apex_symbol: str | None = None,
) -> list[dict[str, Any]]:
    from app.feeds.binance_client import fetch_binance_klines

    return await fetch_binance_klines(
        symbol,
        limit=limit,
        interval=interval,
        market=market,  # type: ignore[arg-type]
        apex_symbol=apex_symbol,
    )


async def fetch_twelvedata_history(
    td_symbol: str,
    apex_symbol: str,
    limit: int = 100,
    interval: str = "1h",
) -> list[dict[str, Any]]:
    from app.services.market_data_store import fetch_bars_from_db

    db_bars = await fetch_bars_from_db(apex_symbol, limit)
    if len(db_bars) >= limit:
        logger.info(
            "twelvedata_bootstrap_db_sufficient",
            symbol=apex_symbol,
            bars=len(db_bars),
        )
        return db_bars

    api_key = settings.twelvedata_api_key
    if not api_key or api_key == "your_key_here":
        logger.warning("twelvedata_bootstrap_skipped", reason="api_key_missing")
        return db_bars

    from app.feeds.twelvedata_limiter import (
        can_afford_credits,
        get_credit_usage_report,
        is_credits_exhausted,
    )

    if await is_credits_exhausted() or not await can_afford_credits(limit):
        logger.warning(
            "twelvedata_bootstrap_skipped_credits",
            symbol=apex_symbol,
            needed=limit,
            **(await get_credit_usage_report()),
        )
        return db_bars

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
                reason="bootstrap",
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
    """Bootstrap: primary feed history → merge DB → DB-only fallback."""
    from app.services.market_data_store import fetch_bars_from_db

    bars = await fetch_history_for_asset(asset, limit)
    if len(bars) >= limit:
        logger.info(
            "history_bootstrap_primary",
            symbol=asset.symbol,
            source=asset.feed_type,
            bars=len(bars),
        )
        return bars[-limit:]

    db_bars = await fetch_bars_from_db(asset.symbol, limit)
    if bars or db_bars:
        seen = {b["timestamp"] for b in bars}
        merged = list(bars)
        for bar in db_bars:
            if bar["timestamp"] not in seen:
                merged.append(bar)
        merged.sort(key=lambda b: b["timestamp"])
        merged = merged[-limit:] if merged else []
        logger.info(
            "history_bootstrap_merged",
            symbol=asset.symbol,
            source=asset.feed_type,
            api_bars=len(bars),
            db_bars=len(db_bars),
            merged=len(merged),
        )
        return merged

    if db_bars:
        logger.info("history_bootstrap_db_fallback", symbol=asset.symbol, bars=len(db_bars))
    return db_bars


async def fetch_history_for_asset(asset: AssetConfig, limit: int = 100) -> list[dict[str, Any]]:
    if asset.feed_type == "binance":
        binance_symbol = asset.binance_symbol or asset.symbol
        try:
            bars = await fetch_binance_history(
                binance_symbol,
                limit,
                asset.candle_interval,
                market=asset.binance_market,
                apex_symbol=asset.symbol,
            )
            if bars:
                return bars
        except Exception as exc:
            logger.warning(
                "binance_history_failed",
                symbol=asset.symbol,
                binance_symbol=binance_symbol,
                error=str(exc)[:200],
            )
        if asset.twelvedata_symbol:
            logger.info("history_bootstrap_twelvedata_fallback", symbol=asset.symbol)
            return await fetch_twelvedata_history(
                asset.twelvedata_symbol,
                asset.symbol,
                limit,
                asset.candle_interval,
            )
        return []
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

    now_iso = datetime.now(timezone.utc).isoformat()
    await set_latest_price(symbol, bar["close"], now_iso)
    await set_feed_last_update(symbol, bar["timestamp"], received_at=now_iso)


async def refresh_dashboard_cache() -> None:
    from app.core.cache import set_dashboard_state
    from app.services.dashboard_builder import build_asset_dashboard_state

    for symbol in ACTIVE_SYMBOLS:
        dashboard = await build_asset_dashboard_state(symbol)
        await set_dashboard_state(symbol, dashboard.model_dump(mode="json"))


async def bootstrap_asset(symbol: str, limit: int | None = None) -> bool:
    """Fetch H1 history, persist to DB, and warm pipeline. Returns True on success."""
    from app.services.market_data_store import persist_bars_batch
    from app.services.pipeline import process_bar

    asset = ASSETS.get(symbol)
    if asset is None:
        return False

    bar_limit = limit if limit is not None else bootstrap_limit_for(asset)
    try:
        bars = await fetch_bootstrap_history(asset, bar_limit)
        if not bars:
            logger.warning("history_bootstrap_empty", symbol=symbol)
            return False

        if asset.feed_type == "binance" and asset.symbol != "XAUUSD" and len(bars) < BINANCE_BOOTSTRAP_BARS:
            logger.warning(
                "history_bootstrap_insufficient_bars",
                symbol=symbol,
                bars=len(bars),
                required=BINANCE_BOOTSTRAP_BARS,
            )

        persisted = await persist_bars_batch(bars)
        logger.info(
            "history_bootstrap_persisted",
            symbol=symbol,
            bars=len(bars),
            persisted=persisted,
        )

        last_bar = bars[-1]
        await process_bar(last_bar, skip_agents=True)
        await _mark_feed_warmed(symbol, last_bar)
        logger.info("history_bootstrap_complete", symbol=symbol, bars=len(bars))
        return len(bars) >= bootstrap_success_threshold(asset, bar_limit)
    except Exception as exc:
        logger.error("history_bootstrap_failed", symbol=symbol, error=str(exc))
        return False


async def warm_asset_from_db(symbol: str, bar_limit: int) -> bool:
    """Seed pipeline from DB without calling external APIs."""
    from app.services.market_data_store import fetch_bars_from_db
    from app.services.pipeline import process_bar

    db_bars = await fetch_bars_from_db(symbol, bar_limit)
    if not db_bars:
        return False

    last_bar = db_bars[-1]
    await process_bar(last_bar, skip_agents=True)
    await _mark_feed_warmed(symbol, last_bar)
    return True


async def bootstrap_all_assets(limit: int | None = None) -> None:
    from app.services.market_data_store import count_bars_in_db, fetch_bars_from_db

    failed: list[str] = []

    for symbol in ACTIVE_SYMBOLS:
        asset = ASSETS[symbol]
        sym_limit = limit if limit is not None else bootstrap_limit_for(asset)
        threshold = bootstrap_success_threshold(asset, sym_limit)
        db_count = await count_bars_in_db(symbol)
        latest = await fetch_bars_from_db(symbol, 1)
        needs_binance_refresh = (
            asset.feed_type == "binance"
            and asset.binance_symbol
            and (not latest or latest[-1].get("source") != "binance")
        )
        if db_count >= threshold and not needs_binance_refresh:
            ok = await warm_asset_from_db(symbol, sym_limit)
            logger.info(
                "history_bootstrap_skipped_db_sufficient",
                symbol=symbol,
                db_bars=db_count,
                threshold=threshold,
            )
        else:
            if needs_binance_refresh:
                logger.info(
                    "history_bootstrap_refresh_stale_source",
                    symbol=symbol,
                    last_source=latest[-1].get("source") if latest else None,
                )
            ok = await bootstrap_asset(symbol, sym_limit)
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
            sym_limit = limit if limit is not None else bootstrap_limit_for(asset)
            required = bootstrap_success_threshold(asset, sym_limit)
            db_count = await count_bars_in_db(symbol)
            if db_count >= required:
                ok = await warm_asset_from_db(symbol, sym_limit)
                if ok:
                    logger.info(
                        "history_bootstrap_db_retry_success",
                        symbol=symbol,
                        bars=db_count,
                    )
                    continue
            ok = await bootstrap_asset(symbol, sym_limit)
            if ok:
                continue
            db_bars = await fetch_bars_from_db(symbol, sym_limit)
            if len(db_bars) >= required:
                if await warm_asset_from_db(symbol, sym_limit):
                    logger.info("history_bootstrap_db_retry_success", symbol=symbol, bars=len(db_bars))
                    continue
            if db_bars:
                logger.warning(
                    "history_bootstrap_db_insufficient_bars",
                    symbol=symbol,
                    bars=len(db_bars),
                    required=required,
                )
            still_failed.append(symbol)
            await asyncio.sleep(1)
        failed = still_failed

    if failed:
        logger.error("history_bootstrap_symbols_failed", symbols=failed)
    await refresh_dashboard_cache()
    from app.services.agent_analysis_service import ensure_agent_consensus_for_active_symbols

    await ensure_agent_consensus_for_active_symbols()
