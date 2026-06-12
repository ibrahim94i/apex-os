"""MetaTrader price ingest — display layer only (no trade execution)."""

from fastapi import APIRouter, Header, HTTPException

from app.config import settings
from app.config.assets import ACTIVE_SYMBOLS
from app.schemas.price import (
    MetaTraderHealthStatus,
    MetaTraderPriceUpdate,
    MetaTraderPriceUpdateResponse,
)
from app.services.live_price_resolver import (
    get_metatrader_health,
    ingest_metatrader_price,
    resolve_display_price,
)

price_router = APIRouter(prefix="/prices", tags=["prices"])


def _verify_metatrader_key(api_key: str | None) -> None:
    if not settings.metatrader_api_key:
        if settings.environment == "production":
            raise HTTPException(status_code=503, detail="MetaTrader API not configured")
        return
    if not api_key or api_key != settings.metatrader_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")


@price_router.post("/update", response_model=MetaTraderPriceUpdateResponse)
async def update_metatrader_price(
    body: MetaTraderPriceUpdate,
    x_mt_key: str | None = Header(default=None, alias="X-MT-Key"),
) -> MetaTraderPriceUpdateResponse:
    """Receive live quotes from MetaTrader EA — prices only, no orders."""
    _verify_metatrader_key(x_mt_key)

    symbol = body.symbol.strip().upper()
    if symbol not in ACTIVE_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol not active: {symbol}")
    if body.ask < body.bid:
        raise HTTPException(status_code=400, detail="ask must be >= bid")

    payload = await ingest_metatrader_price(
        symbol=symbol,
        bid=body.bid,
        ask=body.ask,
        quote_time=body.time,
    )
    return MetaTraderPriceUpdateResponse(
        symbol=symbol,
        price=float(payload["price"]),
        bid=body.bid,
        ask=body.ask,
        received_at=str(payload["received_at"]),
    )


@price_router.get("/status")
async def get_prices_status() -> dict:
    """MetaTrader connection health per active symbol."""
    items = [await get_metatrader_health(sym) for sym in ACTIVE_SYMBOLS]
    return {
        "metatrader": {item.symbol: item.model_dump(mode="json") for item in items},
        "stale_threshold_seconds": settings.metatrader_stale_seconds,
    }


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
    return {
        **data,
        "price_source": data.get("source"),
        "metatrader": health.model_dump(mode="json"),
    }
