"""Live display price resolution — MetaTrader primary, TwelveData fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from app.config import settings
from app.config.assets import get_asset
from app.core.cache import get_metatrader_price, set_display_price, set_metatrader_price
from app.feeds.twelvedata_limiter import throttled_get
from app.logging_config import logger
from app.schemas.price import MetaTraderHealthStatus
from app.utils.time_utils import compute_age_seconds, parse_utc_timestamp
from app.websocket.manager import broadcaster

PriceSource = Literal["metatrader", "twelvedata"]

TWELVEDATA_PRICE_URL = "https://api.twelvedata.com/price"

STATUS_AR = {
    "connected": "MetaTrader متصل",
    "disconnected": "MetaTrader غير متصل",
}


def _mid_price(bid: float, ask: float) -> float:
    return round((bid + ask) / 2, 5)


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _mt_age_seconds(raw: dict[str, Any] | None) -> int | None:
    if not raw:
        return None
    ts_raw = raw.get("received_at") or raw.get("time")
    if not ts_raw:
        return None
    return compute_age_seconds(parse_utc_timestamp(str(ts_raw)))


def is_metatrader_connected(symbol: str, raw: dict[str, Any] | None = None) -> bool:
    data = raw if raw is not None else None
    age = _mt_age_seconds(data)
    if age is None:
        return False
    return age <= settings.metatrader_stale_seconds


async def ingest_metatrader_price(
    *,
    symbol: str,
    bid: float,
    ask: float,
    quote_time: datetime,
) -> dict[str, Any]:
    """Persist MT quote and publish to dashboard display layer."""
    apex_symbol = _normalize_symbol(symbol)
    received_at = datetime.now(timezone.utc)
    if quote_time.tzinfo is None:
        quote_time = quote_time.replace(tzinfo=timezone.utc)
    price = _mid_price(bid, ask)
    payload = {
        "symbol": apex_symbol,
        "bid": bid,
        "ask": ask,
        "price": price,
        "time": quote_time.isoformat(),
        "received_at": received_at.isoformat(),
        "source": "metatrader",
    }
    await set_metatrader_price(apex_symbol, payload)
    await set_display_price(
        apex_symbol,
        price,
        received_at.isoformat(),
        source="metatrader",
    )
    await broadcaster.broadcast_display_price(
        {
            "symbol": apex_symbol,
            "price": price,
            "timestamp": received_at.isoformat(),
            "source": "metatrader",
            "bid": bid,
            "ask": ask,
        }
    )
    logger.info(
        "metatrader_price_ingested",
        symbol=apex_symbol,
        price=price,
        bid=bid,
        ask=ask,
    )
    return payload


async def get_metatrader_health(symbol: str) -> MetaTraderHealthStatus:
    apex_symbol = _normalize_symbol(symbol)
    raw = await get_metatrader_price(apex_symbol)
    age = _mt_age_seconds(raw)
    connected = age is not None and age <= settings.metatrader_stale_seconds
    status = "connected" if connected else "disconnected"
    return MetaTraderHealthStatus(
        symbol=apex_symbol,
        status=status,
        status_ar=STATUS_AR[status],
        connected=connected,
        price_source="metatrader" if connected else None,
        last_update=raw.get("received_at") if raw else None,
        age_seconds=age,
        bid=raw.get("bid") if raw else None,
        ask=raw.get("ask") if raw else None,
        price=raw.get("price") if raw else None,
    )


async def _fetch_twelvedata_display_price(apex_symbol: str) -> dict[str, Any] | None:
    asset = get_asset(apex_symbol)
    td_symbol = asset.twelvedata_symbol if asset else None
    if not td_symbol or not settings.twelvedata_api_key or settings.twelvedata_api_key == "your_key_here":
        return None

    from app.feeds.twelvedata_limiter import should_skip_twelvedata_api

    if await should_skip_twelvedata_api(1):
        return None

    params = {
        "symbol": td_symbol,
        "apikey": settings.twelvedata_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await throttled_get(
                client,
                TWELVEDATA_PRICE_URL,
                params=params,
                reason="mt_price_fallback",
            )
            if response.status_code in (404, 429):
                return None
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("metatrader_twelvedata_fallback_failed", symbol=apex_symbol, error=str(exc))
        return None

    if data.get("status") == "error" or "price" not in data:
        return None

    now = datetime.now(timezone.utc).isoformat()
    price = float(data["price"])
    return {
        "symbol": apex_symbol,
        "price": price,
        "timestamp": now,
        "source": "twelvedata",
    }


async def resolve_display_price(symbol: str) -> dict[str, Any] | None:
    """Primary display price: MetaTrader if fresh, else TwelveData."""
    apex_symbol = _normalize_symbol(symbol)
    mt_raw = await get_metatrader_price(apex_symbol)
    if is_metatrader_connected(apex_symbol, mt_raw) and mt_raw:
        return {
            "symbol": apex_symbol,
            "price": float(mt_raw["price"]),
            "timestamp": mt_raw.get("received_at") or mt_raw.get("time"),
            "source": "metatrader",
            "bid": mt_raw.get("bid"),
            "ask": mt_raw.get("ask"),
        }

    td = await _fetch_twelvedata_display_price(apex_symbol)
    if td:
        await set_display_price(
            apex_symbol,
            td["price"],
            td["timestamp"],
            source="twelvedata",
        )
        return td

    return None
