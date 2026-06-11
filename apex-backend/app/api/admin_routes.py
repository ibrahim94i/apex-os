"""Admin-only maintenance endpoints."""

from fastapi import APIRouter, Header, HTTPException

from app.config import settings
from app.feeds.twelvedata_limiter import reset_twelvedata_credits

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.post("/reset-twelvedata-credits")
async def reset_twelvedata_credits_endpoint(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> dict:
    """Clear today's TwelveData credit flag from Redis and resume API usage."""
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    report = await reset_twelvedata_credits()
    redis_key = f"twelvedata_credits:{report['day']}"
    return {
        "ok": True,
        "redis_key": redis_key,
        "deleted_and_reset": True,
        "credits": report,
    }
