"""End-to-end integration test for the full data pipeline."""

from datetime import datetime, timedelta, timezone

import pytest

from app.engines.indicator_engine import OHLCVBar
from app.engines.signal_generator import SignalGenerator


def _generate_trending_bars(count: int) -> list[OHLCVBar]:
    bars = []
    for i in range(count):
        close = 95000 + i * 50
        bars.append(
            OHLCVBar(
                timestamp=datetime(2026, 5, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                open=close - 20,
                high=close + 30,
                low=close - 30,
                close=close,
                volume=1000.0,
            )
        )
    return bars


def test_full_pipeline_generates_signal() -> None:
    generator = SignalGenerator()
    bars = _generate_trending_bars(60)
    indicators, regime, signal = generator.generate(bars, "BTCUSDT")

    assert indicators is not None
    assert regime is not None
    assert regime.symbol == "BTCUSDT"
    assert indicators.ema_9 is not None

    if signal is not None:
        assert signal.entry_price > 0
        assert signal.stop_loss != signal.take_profit
        assert 0 <= signal.confidence <= 1


def test_pipeline_respects_kill_switch() -> None:
    generator = SignalGenerator()
    bars = _generate_trending_bars(60)
    indicators, regime, signal = generator.generate(bars, "BTCUSDT", kill_switch_active=True)

    assert indicators is not None
    assert regime is not None
    assert signal is None


@pytest.mark.asyncio
async def test_api_health_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient
    from unittest.mock import AsyncMock, patch

    from app.main import app

    with patch("app.api.routes.redis_health_check", new_callable=AsyncMock, return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "database" in data
            assert "redis" in data
