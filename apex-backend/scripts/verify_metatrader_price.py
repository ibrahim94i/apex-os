"""One-shot MetaTrader price layer verification (local AsyncClient)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


async def main() -> None:
    settings.metatrader_api_key = "verify_mt_key"
    settings.metatrader_stale_seconds = 30
    settings.environment = "development"

    body = {
        "symbol": "XAUUSD",
        "bid": 4313.87,
        "ask": 4314.07,
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    td = {
        "symbol": "XAUUSD",
        "price": 4200.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "twelvedata",
    }

    store: dict[str, dict] = {}
    ingest_log: list[dict] = []

    async def fake_set_mt(symbol: str, data: dict) -> None:
        store[f"mt:{symbol}"] = data

    async def fake_get_mt(symbol: str):
        return store.get(f"mt:{symbol}")

    async def fake_set_display(symbol: str, price: float, timestamp: str, *, source: str) -> None:
        store[f"display:{symbol}"] = {"price": price, "timestamp": timestamp, "source": source}

    async def fake_get_display(symbol: str):
        return store.get(f"display:{symbol}")

    async def fake_record(symbol: str, received_at: str) -> None:
        ingest_log.append({"symbol": symbol, "received_at": received_at})

    async def fake_count(symbol: str) -> int:
        return len(ingest_log)

    patches = [
        patch("app.services.live_price_resolver.set_metatrader_price", side_effect=fake_set_mt),
        patch("app.services.live_price_resolver.get_metatrader_price", side_effect=fake_get_mt),
        patch("app.core.cache.get_metatrader_price", side_effect=fake_get_mt),
        patch("app.services.live_price_resolver.set_display_price", side_effect=fake_set_display),
        patch("app.services.live_price_resolver.get_display_price", side_effect=fake_get_display),
        patch("app.core.cache.get_display_price", side_effect=fake_get_display),
        patch("app.services.live_price_resolver.record_metatrader_ingest", side_effect=fake_record),
        patch("app.core.cache.count_metatrader_ingests_last_hour", side_effect=fake_count),
        patch("app.services.live_price_resolver.broadcaster.broadcast_display_price", new=AsyncMock()),
        patch("app.core.redis_client.redis_health_check", new=AsyncMock(return_value=True)),
        patch(
            "app.services.live_price_resolver._fetch_twelvedata_display_price",
            new=AsyncMock(return_value=td),
        ),
    ]

    report: dict = {"steps": []}

    for p in patches:
        p.start()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            bad = await client.post("/api/v1/prices/update", json=body)
            report["steps"].append({"auth_wrong_key": bad.status_code})

            ok = await client.post(
                "/api/v1/prices/update",
                json=body,
                headers={"X-MT-Key": "verify_mt_key"},
            )
            report["steps"].append({"post_ok": ok.status_code, "body": ok.json()})

            live = await client.get("/api/v1/prices/live/XAUUSD")
            report["steps"].append({"live_mt": live.json()})

            diag = await client.get("/api/v1/prices/diagnostics?symbol=XAUUSD")
            report["steps"].append({"diagnostics_mt": diag.json()})

            stale_time = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
            store["mt:XAUUSD"]["received_at"] = stale_time

            live2 = await client.get("/api/v1/prices/live/XAUUSD")
            report["steps"].append({"live_fallback": live2.json()})

            diag2 = await client.get("/api/v1/prices/diagnostics?symbol=XAUUSD")
            report["steps"].append({"diagnostics_fallback": diag2.json()})
    finally:
        for p in patches:
            p.stop()

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
