"""Tests for MetaTrader multi-timeframe candle ingest."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.services.metatrader_candle_ingest import (
    bar_open_from_close_time,
    normalize_metatrader_timeframe,
    parse_metatrader_candle_body,
    parse_metatrader_candle_bootstrap_body,
)
from app.services.metatrader_candle_service import (
    is_metatrader_candles_connected,
    is_metatrader_chart_timeframe_connected,
)
from app.services.metatrader_ingest import verify_metatrader_api_key


@pytest.fixture
def mt_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test_mt_candle_key"
    monkeypatch.setattr(settings, "metatrader_api_key", key)
    monkeypatch.setattr(settings, "metatrader_candle_stale_seconds", 7200)
    return key


def test_normalize_metatrader_timeframe() -> None:
    assert normalize_metatrader_timeframe("1h") == "H1"
    assert normalize_metatrader_timeframe("m5") == "M5"


def test_parse_h1_candle_body_with_close_time() -> None:
    raw = (
        b'{"symbol":"XAUUSD","timeframe":"H1","open":4190.1,"high":4195.2,'
        b'"low":4188.0,"close":4193.5,"volume":1234,"time":"2026.06.12 14:00:00"}\x00'
    )
    parsed = parse_metatrader_candle_body(raw)
    assert parsed["symbol"] == "XAUUSD"
    assert parsed["timeframe"] == "H1"
    assert parsed["open"] == pytest.approx(4190.1)
    assert parsed["close"] == pytest.approx(4193.5)
    assert parsed["timestamp"].hour == 13
    assert parsed["timestamp"].minute == 0


def test_parse_m5_candle_body() -> None:
    raw = (
        b'{"symbol":"XAUUSD","timeframe":"M5","open":4310.0,"high":4312.0,'
        b'"low":4309.0,"close":4311.0,"volume":10,"time":"2026-06-12T14:05:00Z"}'
    )
    parsed = parse_metatrader_candle_body(raw)
    assert parsed["timeframe"] == "M5"
    assert parsed["timestamp"].minute == 0
    assert parsed["timestamp"].second == 0


def test_bar_open_from_close_time_h4() -> None:
    close_time = datetime(2026, 6, 12, 16, 0, tzinfo=timezone.utc)
    bar_open = bar_open_from_close_time(close_time, "H4")
    assert bar_open.hour == 12
    assert bar_open.minute == 0


def test_parse_rejects_unsupported_timeframe() -> None:
    raw = b'{"symbol":"XAUUSD","timeframe":"M30","open":1,"high":2,"low":1,"close":2,"time":"2026-06-12T14:00:00Z"}'
    with pytest.raises(ValueError):
        parse_metatrader_candle_body(raw)


def test_parse_h1_candle_rejects_bad_range() -> None:
    raw = b'{"symbol":"XAUUSD","open":10,"high":9,"low":8,"close":9.5,"time":"2026-06-12T14:00:00Z"}'
    with pytest.raises(ValueError):
        parse_metatrader_candle_body(raw)


@pytest.mark.asyncio
async def test_is_metatrader_candles_connected_fresh() -> None:
    raw = {"last_candle_at": datetime.now(timezone.utc).isoformat()}
    assert await is_metatrader_candles_connected("XAUUSD", raw) is True


@pytest.mark.asyncio
async def test_is_metatrader_chart_timeframe_connected_m5() -> None:
    raw = {
        "timeframes": {
            "M5": {"last_candle_at": datetime.now(timezone.utc).isoformat()},
        }
    }
    assert await is_metatrader_chart_timeframe_connected("XAUUSD", "M5", raw) is True
    assert await is_metatrader_chart_timeframe_connected("XAUUSD", "M15", raw) is False


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


def test_parse_bootstrap_body_with_multiple_candles() -> None:
    candles = []
    for hour in (12, 13, 14):
        candles.append(
            {
                "open": 4190.0 + hour,
                "high": 4195.0 + hour,
                "low": 4188.0 + hour,
                "close": 4193.0 + hour,
                "volume": 10,
                "time": f"2026-06-12T{hour + 1:02d}:00:00Z",
            }
        )
    import json

    raw = json.dumps(
        {"symbol": "XAUUSD", "timeframe": "H1", "candles": candles}
    ).encode()
    parsed = parse_metatrader_candle_bootstrap_body(raw)
    assert parsed["symbol"] == "XAUUSD"
    assert parsed["timeframe"] == "H1"
    assert len(parsed["bars"]) == 3
    assert parsed["bars"][0]["timestamp"] < parsed["bars"][-1]["timestamp"]


def test_parse_bootstrap_rejects_non_h1() -> None:
    import json

    raw = json.dumps(
        {"symbol": "XAUUSD", "timeframe": "M5", "candles": [{"open": 1, "high": 2, "low": 1, "close": 2, "time": "2026-06-12T14:05:00Z"}]}
    ).encode()
    with pytest.raises(ValueError):
        parse_metatrader_candle_bootstrap_body(raw)


@pytest.mark.asyncio
async def test_bootstrap_endpoint(mt_key: str) -> None:
    body = {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "candles": [
            {
                "open": 4190.1,
                "high": 4195.2,
                "low": 4188.0,
                "close": 4193.5,
                "volume": 1000,
                "time": "2026-06-12T14:00:00Z",
            }
        ],
    }
    with patch(
        "app.api.candle_routes.ingest_metatrader_h1_bootstrap",
        new=AsyncMock(
            return_value={
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "received_at": "2026-06-12T14:00:01+00:00",
                "upserted": 1,
                "deleted": 2,
                "oldest": "2026-06-12T13:00:00+00:00",
                "newest": "2026-06-12T13:00:00+00:00",
            }
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/candles/bootstrap",
                json=body,
                headers={"X-MT-Key": mt_key},
            )
    assert response.status_code == 200
    data = response.json()
    assert data["upserted"] == 1
    assert data["deleted"] == 2
    assert data["source"] == "metatrader"
