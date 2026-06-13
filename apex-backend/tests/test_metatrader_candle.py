"""Tests for MetaTrader H1 candle ingest."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.services.metatrader_candle_ingest import parse_metatrader_candle_body
from app.services.metatrader_candle_service import is_metatrader_candles_connected
from app.services.metatrader_ingest import verify_metatrader_api_key


@pytest.fixture
def mt_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test_mt_candle_key"
    monkeypatch.setattr(settings, "metatrader_api_key", key)
    monkeypatch.setattr(settings, "metatrader_candle_stale_seconds", 7200)
    return key


def test_parse_h1_candle_body_with_close_time() -> None:
    raw = (
        b'{"symbol":"XAUUSD","timeframe":"H1","open":4190.1,"high":4195.2,'
        b'"low":4188.0,"close":4193.5,"volume":1234,"time":"2026.06.12 14:00:00"}\x00'
    )
    parsed = parse_metatrader_candle_body(raw)
    assert parsed["symbol"] == "XAUUSD"
    assert parsed["open"] == pytest.approx(4190.1)
    assert parsed["close"] == pytest.approx(4193.5)
    assert parsed["timestamp"].hour == 13
    assert parsed["timestamp"].minute == 0


def test_parse_h1_candle_rejects_bad_range() -> None:
    raw = b'{"symbol":"XAUUSD","open":10,"high":9,"low":8,"close":9.5,"time":"2026-06-12T14:00:00Z"}'
    with pytest.raises(ValueError):
        parse_metatrader_candle_body(raw)


@pytest.mark.asyncio
async def test_is_metatrader_candles_connected_fresh() -> None:
    raw = {"last_candle_at": datetime.now(timezone.utc).isoformat()}
    assert await is_metatrader_candles_connected("XAUUSD", raw) is True


@pytest.mark.asyncio
async def test_candles_update_endpoint(mt_key: str) -> None:
    body = {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "open": 4190.1,
        "high": 4195.2,
        "low": 4188.0,
        "close": 4193.5,
        "volume": 1000,
        "time": "2026-06-12T14:00:00Z",
    }
    with patch(
        "app.api.candle_routes.ingest_metatrader_candle",
        new=AsyncMock(
            return_value={
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "timestamp": "2026-06-12T13:00:00+00:00",
                "received_at": "2026-06-12T14:00:01+00:00",
                "pipeline_ran": True,
            }
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ok = await client.post(
                "/api/v1/candles/update",
                json=body,
                headers={"X-MT-Key": mt_key},
            )
            bad = await client.post("/api/v1/candles/update", json=body)
    assert ok.status_code == 200
    assert ok.json()["source"] == "metatrader"
    assert bad.status_code == 403


def test_verify_metatrader_api_key_for_candles() -> None:
    settings.metatrader_api_key = "secret"
    ok, _ = verify_metatrader_api_key("secret")
    assert ok is True
