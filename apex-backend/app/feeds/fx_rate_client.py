"""FX rate client — free providers in priority order for live FX feeds.

1. exchangerate-api.com (open.er-api.com) — no key
2. fixer.io — FIXER_API_KEY
3. currencyapi.com — CURRENCYAPI_KEY
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.logging_config import logger

EXCHANGE_RATE_API_URL = "https://open.er-api.com/v6/latest"
FIXER_LATEST_URL = "https://data.fixer.io/api/latest"
CURRENCYAPI_LATEST_URL = "https://api.currencyapi.com/v3/latest"
FRANKFURTER_V2_RATES_URL = "https://api.frankfurter.dev/v2/rates"
FRANKFURTER_V2_RATE_URL = "https://api.frankfurter.dev/v2/rate"


def _is_configured(key: str | None) -> bool:
    return bool(key and key not in ("", "your_key_here"))


async def _fetch_exchangerate_api(from_symbol: str, to_symbol: str) -> float | None:
    url = f"{EXCHANGE_RATE_API_URL}/{from_symbol}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    if data.get("result") != "success":
        logger.warning("exchangerate_api_error", message=data.get("result"))
        return None
    rates = data.get("rates") or {}
    rate = rates.get(to_symbol)
    return float(rate) if rate is not None else None


async def _fetch_fixer(from_symbol: str, to_symbol: str) -> float | None:
    if not _is_configured(settings.fixer_api_key):
        return None
    params = {
        "access_key": settings.fixer_api_key,
        "base": from_symbol,
        "symbols": to_symbol,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(FIXER_LATEST_URL, params=params)
        response.raise_for_status()
        data = response.json()
    if not data.get("success"):
        logger.warning("fixer_api_error", error=data.get("error"))
        return None
    rates = data.get("rates") or {}
    rate = rates.get(to_symbol)
    return float(rate) if rate is not None else None


async def _fetch_currencyapi(from_symbol: str, to_symbol: str) -> float | None:
    if not _is_configured(settings.currencyapi_key):
        return None
    params = {
        "apikey": settings.currencyapi_key,
        "base_currency": from_symbol,
        "currencies": to_symbol,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(CURRENCYAPI_LATEST_URL, params=params)
        response.raise_for_status()
        data = response.json()
    currency_data = (data.get("data") or {}).get(to_symbol) or {}
    rate = currency_data.get("value")
    return float(rate) if rate is not None else None


async def fetch_latest_rate_with_source(
    from_symbol: str,
    to_symbol: str,
) -> tuple[float | None, str | None]:
    """Return (rate, provider) trying providers in priority order."""
    providers: list[tuple[str, Any]] = [
        ("exchangerate_api", _fetch_exchangerate_api),
        ("fixer", _fetch_fixer),
        ("currencyapi", _fetch_currencyapi),
    ]
    for name, fetch_fn in providers:
        try:
            rate = await fetch_fn(from_symbol, to_symbol)
            if rate is not None:
                logger.info(
                    "fx_rate_live_ok",
                    from_symbol=from_symbol,
                    to_symbol=to_symbol,
                    source=name,
                    rate=rate,
                )
                return rate, name
        except Exception as exc:
            logger.warning(
                "fx_rate_provider_failed",
                provider=name,
                from_symbol=from_symbol,
                to_symbol=to_symbol,
                error=str(exc),
            )
    logger.warning("fx_rate_all_providers_failed", from_symbol=from_symbol, to_symbol=to_symbol)
    return None, None


async def fetch_latest_rate(from_symbol: str, to_symbol: str) -> float | None:
    rate, _ = await fetch_latest_rate_with_source(from_symbol, to_symbol)
    return rate


async def _fetch_frankfurter_v2_history(
    *,
    from_symbol: str,
    to_symbol: str,
    apex_symbol: str,
    days: int,
) -> list[dict[str, Any]]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    params = {
        "base": from_symbol,
        "quotes": to_symbol,
        "from": start.isoformat(),
        "to": end.isoformat(),
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(FRANKFURTER_V2_RATES_URL, params=params)
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list):
        return []

    bars: list[dict[str, Any]] = []
    for row in rows:
        rate = row.get("rate")
        day_str = row.get("date")
        if rate is None or not day_str:
            continue
        price = float(rate)
        ts = datetime.strptime(day_str, "%Y-%m-%d").replace(
            hour=12, minute=0, second=0, tzinfo=timezone.utc
        )
        bars.append(
            {
                "symbol": apex_symbol,
                "timestamp": ts.isoformat(),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0.0,
                "source": "frankfurter_v2",
                "is_closed": True,
            }
        )
    return bars


async def fetch_historical_daily_bars(
    *,
    from_symbol: str,
    to_symbol: str,
    apex_symbol: str,
    days: int = 365,
) -> list[dict[str, Any]]:
    """Bootstrap history — Frankfurter v2 time series (free, no key)."""
    try:
        bars = await _fetch_frankfurter_v2_history(
            from_symbol=from_symbol,
            to_symbol=to_symbol,
            apex_symbol=apex_symbol,
            days=days,
        )
        if bars:
            logger.info(
                "fx_history_bootstrap_ok",
                symbol=apex_symbol,
                source="frankfurter_v2",
                bars=len(bars),
            )
            return bars
    except Exception as exc:
        logger.warning(
            "fx_history_frankfurter_v2_failed",
            symbol=apex_symbol,
            error=str(exc),
        )

    logger.warning("fx_history_bootstrap_empty", symbol=apex_symbol)
    return []


def build_hourly_bar(
    *,
    apex_symbol: str,
    price: float,
    at: datetime | None = None,
    source: str = "exchangerate_api",
    is_closed: bool = False,
    open_price: float | None = None,
    high: float | None = None,
    low: float | None = None,
) -> dict[str, Any]:
    now = at or datetime.now(timezone.utc)
    ts = now.replace(minute=0, second=0, microsecond=0)
    bar_open = open_price if open_price is not None else price
    bar_high = high if high is not None else price
    bar_low = low if low is not None else price
    return {
        "symbol": apex_symbol,
        "timestamp": ts.isoformat(),
        "open": bar_open,
        "high": bar_high,
        "low": bar_low,
        "close": price,
        "volume": 0.0,
        "source": source,
        "is_closed": is_closed,
    }
