"""Tests for MetaTrader price ingest and live price resolver."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.services.live_price_resolver import (
    get_metatrader_health,
    ingest_metatrader_price,
    is_metatrader_connected,
    resolve_display_price,
)


@pytest.fixture
def mt_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test_mt_key_123"
    monkeypatch.setattr(settings, "metatrader_api_key", key)
    monkeypatch.setattr(settings, "metatrader_stale_seconds", 30)
    return key


@pytest.mark.asyncio
async def test_ingest_and_health_connected() -> None:
    now = datetime.now(timezone.utc)
    with patch("app.services.live_price_resolver.set_metatrader_price", new=AsyncMock()) as mock_set:
        with patch("app.services.live_price_resolver.set_display_price", new=AsyncMock()) as mock_display:
            with patch(
                "app.services.live_price_resolver.broadcaster.broadcast_display_price",
                new=AsyncMock(),
            ):
                payload = await ingest_metatrader_price(
                    symbol="XAUUSD",
                    bid=4313.87,
                    ask=4314.07,
                    quote_time=now,
                )
    assert payload["price"] == pytest.approx(4313.97, rel=1e-4)
    assert payload["source"] == "metatrader"
    mock_set.assert_awaited_once()
    mock_display.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_disconnected_when_stale() -> None:
    stale = {
        "symbol": "XAUUSD",
        "bid": 4310.0,
        "ask": 4310.2,
        "price": 4310.1,
        "received_at": (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat(),
        "source": "metatrader",
    }
    with patch("app.services.live_price_resolver.get_metatrader_price", new=AsyncMock(return_value=stale)):
        health = await get_metatrader_health("XAUUSD")
    assert health.connected is False
    assert health.status == "disconnected"
    assert health.status_ar == "MetaTrader غير متصل"


@pytest.mark.asyncio
async def test_resolve_display_price_prefers_metatrader() -> None:
    fresh = {
        "symbol": "XAUUSD",
        "bid": 4313.87,
        "ask": 4314.07,
        "price": 4313.97,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "metatrader",
    }
    with patch("app.services.live_price_resolver.get_metatrader_price", new=AsyncMock(return_value=fresh)):
        resolved = await resolve_display_price("XAUUSD")
    assert resolved is not None
    assert resolved["source"] == "metatrader"
    assert resolved["price"] == 4313.97


@pytest.mark.asyncio
async def test_resolve_display_price_falls_back_to_twelvedata() -> None:
    stale = {
        "received_at": (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(),
        "price": 4300.0,
    }
    td = {"symbol": "XAUUSD", "price": 4320.5, "timestamp": "2026-06-12T12:00:00+00:00", "source": "twelvedata"}
    with patch("app.services.live_price_resolver.get_metatrader_price", new=AsyncMock(return_value=stale)):
        with patch(
            "app.services.live_price_resolver._fetch_twelvedata_display_price",
            new=AsyncMock(return_value=td),
        ):
            with patch("app.services.live_price_resolver.set_display_price", new=AsyncMock()):
                resolved = await resolve_display_price("XAUUSD")
    assert resolved is not None
    assert resolved["source"] == "twelvedata"


def test_is_metatrader_connected_within_threshold() -> None:
    raw = {"received_at": datetime.now(timezone.utc).isoformat()}
    assert is_metatrader_connected("XAUUSD", raw) is True


@pytest.mark.asyncio
async def test_prices_update_endpoint(mt_key: str) -> None:
    body = {
        "symbol": "XAUUSD",
        "bid": 4313.87,
        "ask": 4314.07,
        "time": "2026-06-12T12:00:00Z",
    }
    with patch(
        "app.api.price_routes.ingest_metatrader_price",
        new=AsyncMock(
            return_value={
                "price": 4313.97,
                "received_at": "2026-06-12T12:00:01+00:00",
            }
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ok = await client.post(
                "/api/v1/prices/update",
                json=body,
                headers={"X-MT-Key": mt_key},
            )
            bad = await client.post("/api/v1/prices/update", json=body)
    assert ok.status_code == 200
    assert ok.json()["price_source"] == "metatrader"
    assert bad.status_code == 403


@pytest.mark.asyncio
async def test_prices_diagnostics_endpoint() -> None:
    mock_diag = {
        "symbol": "XAUUSD",
        "current_source": "twelvedata",
        "metatrader": {"connected": False, "ingests_last_hour": 0},
        "redis": {"status": "ok"},
        "fallback": {"state": "active"},
    }
    with patch(
        "app.api.price_routes.build_price_diagnostics",
        new=AsyncMock(return_value=mock_diag),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/prices/diagnostics?symbol=XAUUSD")
    assert resp.status_code == 200
    assert resp.json()["current_source"] == "twelvedata"


@pytest.mark.asyncio
async def test_prices_status_endpoint() -> None:
    from app.schemas.price import MetaTraderHealthStatus

    mock_health = MetaTraderHealthStatus(
        symbol="XAUUSD",
        status="disconnected",
        status_ar="MetaTrader غير متصل",
        connected=False,
    )
    with patch(
        "app.api.price_routes.get_metatrader_health",
        new=AsyncMock(return_value=mock_health),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/prices/status")
    assert resp.status_code == 200
    assert resp.json()["metatrader"]["XAUUSD"]["status"] == "disconnected"
