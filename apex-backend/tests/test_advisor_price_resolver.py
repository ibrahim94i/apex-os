"""Tests for advisor price staleness resolution."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.advisor_price_resolver import (
    APEX_PRICE_MAX_AGE_SECONDS,
    resolve_advisor_price,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.mark.asyncio
async def test_resolve_fresh_apex_price() -> None:
    fresh_ts = datetime.now(timezone.utc) - timedelta(minutes=2)
    with patch(
        "app.services.advisor_price_resolver.get_latest_price",
        new=AsyncMock(return_value={"price": 4400.0, "timestamp": _iso(fresh_ts)}),
    ):
        info = await resolve_advisor_price("XAUUSD")
    assert info.price == 4400.0
    assert info.apex_price_stale is False
    assert info.price_source == "apex"


@pytest.mark.asyncio
async def test_resolve_stale_apex_price_rejected() -> None:
    stale_ts = datetime.now(timezone.utc) - timedelta(minutes=30)
    with patch(
        "app.services.advisor_price_resolver.get_latest_price",
        new=AsyncMock(return_value={"price": 4300.0, "timestamp": _iso(stale_ts)}),
    ):
        info = await resolve_advisor_price("XAUUSD")
    assert info.price is None
    assert info.apex_price == 4300.0
    assert info.apex_price_stale is True
    assert info.price_source == "stale"


@pytest.mark.asyncio
async def test_resolve_missing_apex_price() -> None:
    with patch(
        "app.services.advisor_price_resolver.get_latest_price",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.services.advisor_price_resolver.get_latest_price_from_db",
            new=AsyncMock(return_value=None),
        ):
            info = await resolve_advisor_price("EURUSD")
    assert info.price is None
    assert info.apex_price_stale is True
    assert info.price_source == "unavailable"


@pytest.mark.asyncio
async def test_resolve_stale_boundary() -> None:
    stale_ts = datetime.now(timezone.utc) - timedelta(
        seconds=APEX_PRICE_MAX_AGE_SECONDS + 1
    )
    with patch(
        "app.services.advisor_price_resolver.get_latest_price",
        new=AsyncMock(return_value={"price": 1.08, "timestamp": _iso(stale_ts)}),
    ):
        info = await resolve_advisor_price("EURUSD")
    assert info.price is None
    assert info.price_source == "stale"
