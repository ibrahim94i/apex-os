"""Resolve advisor reference price from fresh APEX data only (<10 min)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.cache import get_latest_price
from app.services.market_data_store import get_latest_price_from_db
from app.utils.time_utils import compute_age_seconds, parse_utc_timestamp

APEX_PRICE_MAX_AGE_SECONDS = 600  # 10 minutes


@dataclass(frozen=True)
class AdvisorPriceInfo:
    price: float | None
    apex_price: float | None
    price_timestamp: datetime | None
    price_age_minutes: float | None
    apex_price_stale: bool
    price_source: str


async def resolve_advisor_price(symbol: str) -> AdvisorPriceInfo:
    """Fresh APEX (<10 min) only — no external sources."""
    price_data = await get_latest_price(symbol)
    if not price_data:
        price_data = await get_latest_price_from_db(symbol)
    if not price_data:
        return AdvisorPriceInfo(
            price=None,
            apex_price=None,
            price_timestamp=None,
            price_age_minutes=None,
            apex_price_stale=True,
            price_source="unavailable",
        )

    apex_price = float(price_data["price"])
    raw_ts = price_data.get("timestamp")
    if not raw_ts:
        return AdvisorPriceInfo(
            price=None,
            apex_price=apex_price,
            price_timestamp=None,
            price_age_minutes=None,
            apex_price_stale=True,
            price_source="unavailable",
        )

    ts = parse_utc_timestamp(raw_ts)
    age_sec = compute_age_seconds(ts)
    age_min = age_sec / 60.0
    stale = age_sec > APEX_PRICE_MAX_AGE_SECONDS

    if stale:
        return AdvisorPriceInfo(
            price=None,
            apex_price=apex_price,
            price_timestamp=ts,
            price_age_minutes=age_min,
            apex_price_stale=True,
            price_source="stale",
        )

    return AdvisorPriceInfo(
        price=apex_price,
        apex_price=apex_price,
        price_timestamp=ts,
        price_age_minutes=age_min,
        apex_price_stale=False,
        price_source="apex",
    )
