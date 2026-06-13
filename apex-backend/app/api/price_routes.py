"""MetaTrader price ingest — analysis + display layer (no trade execution)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.config.assets import ACTIVE_SYMBOLS
from app.logging_config import logger
from app.schemas.price import MetaTraderPriceUpdateResponse
from app.services.live_price_resolver import (
    build_price_diagnostics,
    get_metatrader_health,
    ingest_metatrader_price,
    resolve_display_price,
)
from app.core.cache import get_metatrader_price
from app.services.metatrader_ingest import (
    MT_AUTH_HEADER,
    extract_mt_api_key,
    parse_metatrader_request_body,
    sanitize_headers_for_log,
    verify_metatrader_api_key,
)

price_router = APIRouter(prefix="/prices", tags=["prices"])


@price_router.post("/update", response_model=MetaTraderPriceUpdateResponse)
async def update_metatrader_price(request: Request) -> MetaTraderPriceUpdateResponse:
    """Receive live quotes from MetaTrader EA — analysis + display price layer."""
    raw_body = await request.body()
    headers = {k: v for k, v in request.headers.items()}
    header_log = sanitize_headers_for_log(headers)
    body_preview = raw_body.decode("utf-8", errors="replace")[:2000]

    logger.info(
        "metatrader_request_received",
        method=request.method,
        path=str(request.url.path),
        headers=header_log,
        body=body_preview,
        body_bytes=len(raw_body),
    )

    received_key = extract_mt_api_key(headers)
    ok, auth_error = verify_metatrader_api_key(received_key)
    if not ok:
        logger.warning(
            "metatrader_auth_failed",
            reason=auth_error,
            received_key=received_key,
            header_name=MT_AUTH_HEADER,
            key_configured=bool((settings.metatrader_api_key or "").strip()),
        )
        if auth_error and "not configured" in auth_error.lower():
            raise HTTPException(status_code=503, detail=auth_error)
        raise HTTPException(
            status_code=403,
            detail={"error": "Forbidden", "reason": auth_error, "header": MT_AUTH_HEADER},
        )

    try:
        parsed = parse_metatrader_request_body(raw_body)
    except ValueError as exc:
        logger.warning(
            "metatrader_request_parse_failed",
            error=str(exc),
            body=body_preview,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    symbol = parsed["symbol"]
    if symbol not in ACTIVE_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol not active: {symbol}")

    try:
        payload = await ingest_metatrader_price(
            symbol=symbol,
            bid=parsed["bid"],
            ask=parsed["ask"],
            quote_time=parsed["time"],
        )
    except Exception as exc:
        logger.error(
            "metatrader_redis_write_failed",
            symbol=symbol,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to persist MetaTrader price") from exc

    return MetaTraderPriceUpdateResponse(
        symbol=symbol,
        price=float(payload["price"]),
        bid=parsed["bid"],
        ask=parsed["ask"],
        received_at=str(payload["received_at"]),
    )


@price_router.get("/status")
async def get_prices_status() -> dict[str, Any]:
    """MetaTrader connection health per active symbol (Redis last update age)."""
    items = [await get_metatrader_health(sym) for sym in ACTIVE_SYMBOLS]
    return {
        "metatrader": {item.symbol: item.model_dump(mode="json") for item in items},
        "stale_threshold_seconds": settings.metatrader_stale_seconds,
    }


@price_router.get("/diagnostics")
async def get_prices_diagnostics(symbol: str = "XAUUSD") -> dict:
    """Verification snapshot — MetaTrader ingest, Redis, fallback, and active source."""
    sym = symbol.strip().upper()
    if sym not in ACTIVE_SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not active")
    return await build_price_diagnostics(sym)


@price_router.get("/live/{symbol}")
async def get_live_display_price(symbol: str) -> dict:
    """Resolved display price (MetaTrader → TwelveData)."""
    sym = symbol.strip().upper()
    if sym not in ACTIVE_SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not active")
    data = await resolve_display_price(sym)
    if not data:
        raise HTTPException(status_code=404, detail="No live price available")
    health = await get_metatrader_health(sym)
    mt_raw = await get_metatrader_price(sym)
    received_at = None
    if mt_raw:
        received_at = mt_raw.get("received_at")
    elif data.get("source") == "twelvedata":
        received_at = data.get("timestamp")
    return {
        **data,
        "price_source": data.get("source"),
        "received_at": received_at or data.get("timestamp"),
        "age_seconds": health.age_seconds if data.get("source") == "metatrader" else None,
        "metatrader": health.model_dump(mode="json"),
    }
