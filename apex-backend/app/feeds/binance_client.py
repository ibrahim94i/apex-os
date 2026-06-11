"""Binance public REST klines client — no API key required."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from app.logging_config import logger

BinanceMarket = Literal["spot", "futures"]

# Spot mirror (geo-friendly). XAUUSDT is futures-only — use binance_market="futures".
BINANCE_KLINES_URLS: tuple[str, ...] = (
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
    "https://api1.binance.com/api/v3/klines",
    "https://api2.binance.com/api/v3/klines",
    "https://api3.binance.com/api/v3/klines",
)
BINANCE_FUTURES_KLINES_URLS: tuple[str, ...] = (
    "https://fapi.binance.com/fapi/v1/klines",
)
BINANCE_TICKER_URLS: tuple[str, ...] = (
    "https://data-api.binance.vision/api/v3/ticker/price",
    "https://api.binance.com/api/v3/ticker/price",
)
BINANCE_FUTURES_TICKER_URLS: tuple[str, ...] = (
    "https://fapi.binance.com/fapi/v1/ticker/price",
)


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


def _klines_urls(market: BinanceMarket) -> tuple[str, ...]:
    if market == "futures":
        return BINANCE_FUTURES_KLINES_URLS + BINANCE_KLINES_URLS
    return BINANCE_KLINES_URLS


def _ticker_urls(market: BinanceMarket) -> tuple[str, ...]:
    if market == "futures":
        return BINANCE_FUTURES_TICKER_URLS + BINANCE_TICKER_URLS
    return BINANCE_TICKER_URLS


async def _get_json(url: str, params: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def fetch_binance_klines(
    symbol: str,
    *,
    limit: int = 100,
    interval: str = "1h",
    market: BinanceMarket = "spot",
    apex_symbol: str | None = None,
) -> list[dict[str, Any]]:
    bar_symbol = apex_symbol or symbol
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    last_error: Exception | None = None
    for url in _klines_urls(market):
        try:
            rows = await _get_json(url, params)
            if not isinstance(rows, list):
                continue
            logger.debug("binance_klines_ok", symbol=symbol, url=url.split("/")[2], market=market)
            return [kline_row_to_bar(bar_symbol, row) for row in rows]
        except Exception as exc:
            last_error = exc
            logger.warning(
                "binance_klines_endpoint_failed",
                symbol=symbol,
                url=url.split("/")[2],
                market=market,
                error=str(exc)[:160],
            )
    raise RuntimeError(f"All Binance klines endpoints failed for {symbol}: {last_error}")


async def fetch_binance_ticker_price(
    symbol: str,
    *,
    market: BinanceMarket = "spot",
) -> float | None:
    params = {"symbol": symbol}
    for url in _ticker_urls(market):
        try:
            data = await _get_json(url, params)
            price = float(data["price"])
            logger.debug("binance_ticker_ok", symbol=symbol, url=url.split("/")[2], market=market)
            return price
        except Exception as exc:
            logger.warning(
                "binance_ticker_endpoint_failed",
                symbol=symbol,
                url=url.split("/")[2],
                market=market,
                error=str(exc)[:160],
            )
    return None


async def fetch_binance_latest_bar(
    symbol: str,
    *,
    interval: str = "1h",
    market: BinanceMarket = "spot",
    apex_symbol: str | None = None,
) -> dict[str, Any] | None:
    bar_symbol = apex_symbol or symbol
    try:
        bars = await fetch_binance_klines(
            symbol,
            limit=2,
            interval=interval,
            market=market,
            apex_symbol=bar_symbol,
        )
        if bars:
            return bars[-1]
    except Exception as exc:
        logger.warning("binance_klines_fetch_failed", symbol=symbol, market=market, error=str(exc)[:200])

    price = await fetch_binance_ticker_price(symbol, market=market)
    if price is None:
        return None

    now = datetime.now(timezone.utc)
    return {
        "symbol": bar_symbol,
        "timestamp": now.isoformat(),
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": 0.0,
        "source": "binance",
        "is_closed": False,
    }
