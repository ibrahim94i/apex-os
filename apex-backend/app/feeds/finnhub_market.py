"""Finnhub OHLC market data — bootstrap history and live price fallback."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.logging_config import logger

FINNHUB_CANDLE_URL = "https://finnhub.io/api/v1/forex/candle"
FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
FINNHUB_RATES_URL = "https://finnhub.io/api/v1/forex/rates"

_lock = asyncio.Lock()
_last_request_at: float = 0.0

RESOLUTION_MAP = {
    "1h": "60",
    "60min": "60",
    "30min": "30",
    "15min": "15",
    "5min": "5",
    "1min": "1",
}


def _is_configured() -> bool:
    key = settings.finnhub_api_key
    return bool(key and key not in ("", "your_key_here"))


def _auth_headers() -> dict[str, str]:
    return {"X-Finnhub-Token": settings.finnhub_api_key}


def _parse_oanda_pair(finnhub_symbol: str) -> tuple[str, str] | None:
    if ":" not in finnhub_symbol:
        return None
    pair = finnhub_symbol.split(":", 1)[1]
    parts = pair.split("_")
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


async def _throttled_get(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    global _last_request_at
    min_gap = settings.finnhub_market_min_gap_seconds
    request_headers = headers or _auth_headers()
    async with _lock:
        now = time.monotonic()
        wait = min_gap - (now - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        response = await client.get(url, params=params, headers=request_headers)
        _last_request_at = time.monotonic()
        return response


def _normalize_bar(
    symbol: str,
    timestamp: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
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
        "source": "finnhub",
        "is_closed": True,
    }


def _parse_candle_payload(
    apex_symbol: str,
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    if data.get("s") != "ok":
        return []
    times = data.get("t") or []
    if not times:
        return []
    opens = data.get("o") or []
    highs = data.get("h") or []
    lows = data.get("l") or []
    closes = data.get("c") or []
    volumes = data.get("v") or []

    bars: list[dict[str, Any]] = []
    for idx, ts in enumerate(times):
        ts_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        vol = float(volumes[idx]) if idx < len(volumes) else 0.0
        bars.append(
            _normalize_bar(
                symbol=apex_symbol,
                timestamp=ts_dt,
                open_=float(opens[idx]),
                high=float(highs[idx]),
                low=float(lows[idx]),
                close=float(closes[idx]),
                volume=vol,
            )
        )
    return bars


async def fetch_finnhub_history(
    apex_symbol: str,
    finnhub_symbol: str,
    *,
    limit: int = 250,
    interval: str = "1h",
) -> list[dict[str, Any]]:
    """Fetch historical H1 candles from Finnhub (bootstrap primary source)."""
    if not _is_configured():
        logger.warning("finnhub_market_skipped", reason="api_key_missing", symbol=apex_symbol)
        return []

    resolution = RESOLUTION_MAP.get(interval, "60")
    params = {
        "symbol": finnhub_symbol,
        "resolution": resolution,
        "count": limit,
        "token": settings.finnhub_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await _throttled_get(client, FINNHUB_CANDLE_URL, params)
            if response.status_code == 403:
                logger.warning(
                    "finnhub_premium_required",
                    symbol=apex_symbol,
                    finnhub_symbol=finnhub_symbol,
                    endpoint="forex/candle",
                )
                return []
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            logger.warning(
                "finnhub_premium_required",
                symbol=apex_symbol,
                finnhub_symbol=finnhub_symbol,
                endpoint="forex/candle",
            )
            return []
        logger.warning(
            "finnhub_history_fetch_failed",
            symbol=apex_symbol,
            finnhub_symbol=finnhub_symbol,
            error=str(exc),
        )
        return []
    except Exception as exc:
        logger.warning(
            "finnhub_history_fetch_failed",
            symbol=apex_symbol,
            finnhub_symbol=finnhub_symbol,
            error=str(exc),
        )
        return []

    bars = _parse_candle_payload(apex_symbol, data)
    if bars:
        logger.info(
            "finnhub_history_fetched",
            symbol=apex_symbol,
            bars=len(bars),
            finnhub_symbol=finnhub_symbol,
        )
    else:
        logger.warning(
            "finnhub_history_empty",
            symbol=apex_symbol,
            finnhub_symbol=finnhub_symbol,
            status=data.get("s"),
        )
    return bars


async def fetch_finnhub_latest_bar(
    apex_symbol: str,
    finnhub_symbol: str,
    *,
    interval: str = "1h",
) -> dict[str, Any] | None:
    """Fetch live price from Finnhub: candle → forex/rates → quote."""
    bars = await fetch_finnhub_history(
        apex_symbol,
        finnhub_symbol,
        limit=1,
        interval=interval,
    )
    if bars:
        return bars[-1]
    if not _is_configured():
        return None

    pair = _parse_oanda_pair(finnhub_symbol)
    if pair:
        base, quote = pair
        params = {"base": base, "token": settings.finnhub_api_key}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await _throttled_get(client, FINNHUB_RATES_URL, params)
                if response.status_code == 403:
                    logger.warning(
                        "finnhub_premium_required",
                        symbol=apex_symbol,
                        endpoint="forex/rates",
                    )
                else:
                    response.raise_for_status()
                    data = response.json()
                    rate = (data.get("quote") or {}).get(quote)
                    if rate is not None:
                        px = float(rate)
                        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
                        logger.info(
                            "finnhub_rates_bar",
                            symbol=apex_symbol,
                            base=base,
                            quote=quote,
                            price=px,
                        )
                        return _normalize_bar(
                            symbol=apex_symbol,
                            timestamp=now,
                            open_=px,
                            high=px,
                            low=px,
                            close=px,
                            volume=0.0,
                        )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                logger.warning(
                    "finnhub_rates_fetch_failed",
                    symbol=apex_symbol,
                    error=str(exc),
                )
        except Exception as exc:
            logger.warning("finnhub_rates_fetch_failed", symbol=apex_symbol, error=str(exc))

    params = {"symbol": finnhub_symbol, "token": settings.finnhub_api_key}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await _throttled_get(client, FINNHUB_QUOTE_URL, params)
            if response.status_code == 403:
                logger.warning(
                    "finnhub_premium_required",
                    symbol=apex_symbol,
                    endpoint="quote",
                )
                return None
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            logger.warning(
                "finnhub_premium_required",
                symbol=apex_symbol,
                endpoint="quote",
            )
            return None
        logger.warning(
            "finnhub_quote_fetch_failed",
            symbol=apex_symbol,
            error=str(exc),
        )
        return None
    except Exception as exc:
        logger.warning(
            "finnhub_quote_fetch_failed",
            symbol=apex_symbol,
            error=str(exc),
        )
        return None

    price = data.get("c")
    ts = data.get("t")
    if price is None or not ts:
        return None

    ts_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    px = float(price)
    return _normalize_bar(
        symbol=apex_symbol,
        timestamp=ts_dt,
        open_=px,
        high=px,
        low=px,
        close=px,
        volume=0.0,
    )
