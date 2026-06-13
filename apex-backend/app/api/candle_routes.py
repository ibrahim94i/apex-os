"""MetaTrader H1 candle ingest — replaces Binance H1 for XAUUSD when connected."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.config.assets import ACTIVE_SYMBOLS
from app.logging_config import logger
from app.schemas.candle import MetaTraderCandleUpdateResponse
from app.services.metatrader_candle_ingest import parse_metatrader_candle_body
from app.services.metatrader_candle_service import (
    ingest_metatrader_candle,
    is_metatrader_candles_connected,
)
from app.services.metatrader_ingest import (
    MT_AUTH_HEADER,
    extract_mt_api_key,
    sanitize_headers_for_log,
    verify_metatrader_api_key,
)
from app.core.cache import get_metatrader_candle_state

candle_router = APIRouter(prefix="/candles", tags=["candles"])


@candle_router.post("/update", response_model=MetaTraderCandleUpdateResponse)
async def update_metatrader_candle(request: Request) -> MetaTraderCandleUpdateResponse:
    """Receive closed H1 OHLCV from MetaTrader EA."""
    raw_body = await request.body()
    headers = {k: v for k, v in request.headers.items()}
    body_preview = raw_body.decode("utf-8", errors="replace")[:2000]

    logger.info(
        "metatrader_candle_request_received",
        method=request.method,
        path=str(request.url.path),
        headers=sanitize_headers_for_log(headers),
        body=body_preview,
        body_bytes=len(raw_body),
    )

    received_key = extract_mt_api_key(headers)
    ok, auth_error = verify_metatrader_api_key(received_key)
    if not ok:
        logger.warning(
            "metatrader_candle_auth_failed",
            reason=auth_error,
            header_name=MT_AUTH_HEADER,
        )
        if auth_error and "not configured" in auth_error.lower():
            raise HTTPException(status_code=503, detail=auth_error)
        raise HTTPException(
            status_code=403,
            detail={"error": "Forbidden", "reason": auth_error, "header": MT_AUTH_HEADER},
        )

    try:
        parsed = parse_metatrader_candle_body(raw_body)
    except ValueError as exc:
        logger.warning("metatrader_candle_parse_failed", error=str(exc), body=body_preview)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    symbol = parsed["symbol"]
    if symbol not in ACTIVE_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol not active: {symbol}")

    try:
        result = await ingest_metatrader_candle(parsed)
    except Exception as exc:
        logger.error("metatrader_candle_persist_failed", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to persist MetaTrader candle") from exc

    return MetaTraderCandleUpdateResponse(
        symbol=result["symbol"],
        timeframe=result["timeframe"],
        timestamp=result["timestamp"],
        received_at=result["received_at"],
        pipeline_ran=result["pipeline_ran"],
    )


@candle_router.get("/status")
async def get_candles_status() -> dict[str, Any]:
    """MetaTrader H1 candle feed health per active symbol."""
    items: dict[str, Any] = {}
    for sym in ACTIVE_SYMBOLS:
        raw = await get_metatrader_candle_state(sym)
        connected = await is_metatrader_candles_connected(sym, raw)
        items[sym] = {
            "symbol": sym,
            "connected": connected,
            "status": "connected" if connected else "disconnected",
            "status_ar": "MetaTrader H1 متصل" if connected else "MetaTrader H1 غير متصل",
            "last_candle_at": raw.get("last_candle_at") if raw else None,
            "received_at": raw.get("received_at") if raw else None,
            "source": raw.get("source") if raw else None,
            "stale_threshold_seconds": settings.metatrader_candle_stale_seconds,
        }
    return {"metatrader_candles": items}
