"""Resolve effective advisor reference price — reject stale APEX (>10 min)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.config.assets import get_asset
from app.core.cache import get_latest_price
from app.logging_config import logger
from app.services.market_data_store import get_latest_price_from_db
from app.utils.time_utils import compute_age_seconds, parse_utc_timestamp

APEX_PRICE_MAX_AGE_SECONDS = 600  # 10 minutes


@dataclass(frozen=True)
class AdvisorPriceInfo:
    """Effective price for intraday advisor (entry band, SL/TP reference)."""

    price: float | None
    apex_price: float | None
    price_timestamp: datetime | None
    price_age_minutes: float | None
    apex_price_stale: bool
    price_source: str
    price_requires_web: bool


async def _load_apex_price(symbol: str) -> tuple[float | None, datetime | None, float | None]:
    price_data = await get_latest_price(symbol)
    if not price_data:
        price_data = await get_latest_price_from_db(symbol)
    if not price_data:
        return None, None, None

    apex_price = float(price_data["price"])
    raw_ts = price_data.get("timestamp")
    if not raw_ts:
        return apex_price, None, None

    ts = parse_utc_timestamp(raw_ts)
    age_sec = compute_age_seconds(ts)
    return apex_price, ts, age_sec / 60.0


async def _fetch_live_fallback_price(symbol: str) -> tuple[float | None, str | None]:
    asset = get_asset(symbol)
    if not asset:
        return None, None
    try:
        from app.feeds.live_price_fallback import fetch_live_fallback_bar

        bar, source = await fetch_live_fallback_bar(asset)
    except Exception as exc:
        logger.warning("advisor_live_fallback_failed", symbol=symbol, error=str(exc))
        return None, None
    if not bar:
        return None, None
    return float(bar["close"]), source


async def resolve_advisor_price(symbol: str) -> AdvisorPriceInfo:
    """Fresh APEX (<10 min) → use it; else live fallback; else require web search."""
    apex_price, apex_ts, apex_age_min = await _load_apex_price(symbol)
    apex_stale = True
    if apex_price is not None and apex_ts is not None:
        apex_stale = compute_age_seconds(apex_ts) > APEX_PRICE_MAX_AGE_SECONDS
    elif apex_price is not None:
        apex_stale = True

    if apex_price is not None and not apex_stale:
        return AdvisorPriceInfo(
            price=apex_price,
            apex_price=apex_price,
            price_timestamp=apex_ts,
            price_age_minutes=apex_age_min,
            apex_price_stale=False,
            price_source="apex",
            price_requires_web=False,
        )

    live_price, live_source = await _fetch_live_fallback_price(symbol)
    if live_price is not None:
        source_label = f"live_fallback:{live_source}" if live_source else "live_fallback"
        return AdvisorPriceInfo(
            price=live_price,
            apex_price=apex_price if apex_stale else None,
            price_timestamp=datetime.now(timezone.utc),
            price_age_minutes=0.0,
            apex_price_stale=apex_stale or apex_price is None,
            price_source=source_label,
            price_requires_web=False,
        )

    return AdvisorPriceInfo(
        price=None,
        apex_price=apex_price if apex_stale else None,
        price_timestamp=apex_ts if apex_stale else None,
        price_age_minutes=apex_age_min,
        apex_price_stale=apex_stale or apex_price is None,
        price_source="web_required",
        price_requires_web=True,
    )
