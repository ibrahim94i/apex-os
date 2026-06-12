"""Tests for MetaTrader ingest parsing, auth, and price layer."""

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
from app.services.metatrader_ingest import (
    extract_mt_api_key,
    parse_metatrader_request_body,
    verify_metatrader_api_key,
)


@pytest.fixture
def mt_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test_mt_key_123"
    monkeypatch.setattr(settings, "metatrader_api_key", key)
    monkeypatch.setattr(settings, "metatrader_stale_seconds", 30)
    return key


def test_parse_mt_body_flexible_time_and_strings() -> None:
    raw = b'{"symbol":"XAUUSD","bid":"4313.87","ask":"4314.07","time":"2026.06.12 12:00:00"}'
    parsed = parse_metatrader_request_body(raw)
    assert parsed["symbol"] == "XAUUSD"
    assert parsed["bid"] == pytest.approx(4313.87)
    assert parsed["ask"] == pytest.approx(4314.07)


def test_extract_mt_api_key_case_insensitive() -> None:
    assert extract_mt_api_key({"x-mt-key": "abc"}) == "abc"
    assert extract_mt_api_key({"X-MT-Key": " abc "}) == "abc"


def test_verify_metatrader_api_key() -> None:
    settings.metatrader_api_key = "secret"
    ok, err = verify_metatrader_api_key("secret")
    assert ok is True
    ok, err = verify_metatrader_api_key("wrong")
    assert ok is False
    assert err == "Invalid X-MT-Key"


@pytest.mark.asyncio
async def test_ingest_and_health_connected() -> None:
    now = datetime.now(timezone.utc)
    with patch("app.services.live_price_resolver.set_metatrader_price", new=AsyncMock()) as mock_set:
        with patch("app.services.live_price_resolver.set_display_price", new=AsyncMock()) as mock_display:
            with patch("app.services.live_price_resolver.record_metatrader_ingest", new=AsyncMock()):
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
async def test_prices_update_mt4_dot_date_format(mt_key: str) -> None:
    raw_json = '{"symbol":"XAUUSD","bid":4313.87,"ask":4314.07,"time":"2026.06.12 12:00:00"}'
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
            resp = await client.post(
                "/api/v1/prices/update",
                content=raw_json,
                headers={
                    "Content-Type": "application/json",
                    "X-MT-Key": mt_key,
                },
            )
    assert resp.status_code == 200


def test_is_metatrader_connected_within_threshold() -> None:
    raw = {"received_at": datetime.now(timezone.utc).isoformat()}
    assert is_metatrader_connected("XAUUSD", raw) is True
