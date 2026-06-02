"""Phase 3 end-to-end tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.voting.weighted_engine import AdaptiveWeightedEngine
from app.config.assets import ASSETS, ACTIVE_SYMBOLS
from app.models.phase3 import MemoryPattern
from app.schemas import SignalDirection
from app.schemas.agent import AgentRole, AgentVerdict
from app.services.alert_service import AlertService, AlertType
from app.services.backtester import Backtester
from app.services.memory_engine import memory_engine, time_of_day


def test_multi_asset_config() -> None:
    assert "BTCUSDT" in ASSETS
    assert "XAUUSD" in ASSETS
    assert "EURUSD" in ASSETS
    assert len(ACTIVE_SYMBOLS) == 3
    assert ASSETS["XAUUSD"].feed_type == "twelvedata"
    assert ASSETS["EURUSD"].feed_type == "twelvedata"
    assert ASSETS["EURUSD"].market_schedule == "forex_24_5"
    assert ASSETS["BTCUSDT"].feed_type == "twelvedata"
    assert ASSETS["BTCUSDT"].twelvedata_symbol == "BTC/USD"


def test_time_of_day_buckets() -> None:
    assert time_of_day(8) == "morning"
    assert time_of_day(14) == "afternoon"
    assert time_of_day(19) == "evening"
    assert time_of_day(2) == "night"


@pytest.mark.asyncio
async def test_adaptive_weights_risk_minimum() -> None:
    engine = AdaptiveWeightedEngine()
    verdicts = [
        AgentVerdict(
            agent_id=AgentRole.MARKET_ANALYST,
            agent_name_ar="محلل",
            direction=SignalDirection.LONG,
            confidence=0.8,
            reasoning=["test"],
            weight=0.4,
        ),
        AgentVerdict(
            agent_id=AgentRole.RISK,
            agent_name_ar="مخاطر",
            direction=SignalDirection.LONG,
            confidence=0.7,
            reasoning=["test"],
            weight=0.35,
        ),
        AgentVerdict(
            agent_id=AgentRole.NEWS,
            agent_name_ar="أخبار",
            direction=SignalDirection.NEUTRAL,
            confidence=0.5,
            reasoning=["test"],
            weight=0.25,
        ),
    ]
    weights = await engine.compute_weights(None, "BTCUSDT", "TRENDING_UP", verdicts)
    assert weights[AgentRole.RISK] >= 0.40
    assert abs(sum(weights.values()) - 1.0) < 0.01


@pytest.mark.asyncio
async def test_alert_service_high_confidence() -> None:
    service = AlertService()
    with patch.object(service, "_should_send", new_callable=AsyncMock, return_value=True):
        with patch.object(service, "_push", new_callable=AsyncMock) as mock_push:
            alert = await service.notify_new_signal("BTCUSDT", "LONG", 0.85)
            assert alert.type == AlertType.HIGH_CONFIDENCE
            assert alert.fullscreen is True
            mock_push.assert_called_once()


@pytest.mark.asyncio
async def test_alert_kill_switch_fullscreen() -> None:
    service = AlertService()
    with patch.object(service, "_push", new_callable=AsyncMock):
        alert = await service.check_kill_switch(True, "test reason")
        assert alert is not None
        assert alert.fullscreen is True


@pytest.mark.asyncio
async def test_backtest_api_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.services.backtester import BacktestResults

    mock_results = BacktestResults(symbol="ALL", total_signals=0, evaluated=0)

    with patch("app.api.phase3_routes.backtester.run", new_callable=AsyncMock, return_value=mock_results):
        with patch("app.api.phase3_routes.memory_engine.update_from_signals", new_callable=AsyncMock, return_value=0):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/backtest/run")
                assert response.status_code == 200


@pytest.mark.asyncio
async def test_multi_dashboard_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.schemas import KillSwitchStatus, KillSwitchStatusSchema

    ks = KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE)

    with patch("app.api.phase3_routes.build_asset_dashboard_state", new_callable=AsyncMock) as mock_build:
        from app.schemas import DashboardStateSchema

        mock_build.return_value = DashboardStateSchema(
            symbol="BTCUSDT",
            kill_switch=KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE),
        )
        with patch("app.api.phase3_routes.memory_engine.get_top_patterns", new_callable=AsyncMock, return_value=[]):
            with patch(
                "app.api.phase3_routes.memory_engine.get_memory_summary",
                new_callable=AsyncMock,
                return_value={"symbol": "BTCUSDT", "overall_win_rate": 0, "total_samples": 0},
            ):
                with patch("app.api.phase3_routes.kill_switch.evaluate", new_callable=AsyncMock, return_value=ks):
                    with patch("app.api.phase3_routes.kill_switch.load_from_cache", new_callable=AsyncMock):
                        with patch(
                            "app.api.phase3_routes.account_service.get_status",
                            new_callable=AsyncMock,
                            return_value={"mode": "demo", "balance": 10000.0, "label_ar": "تجريبي"},
                        ):
                            with patch("app.api.phase3_routes.build_all_market_statuses", new_callable=AsyncMock, return_value={}):
                                with patch("app.api.phase3_routes.get_hourly_report", new_callable=AsyncMock, return_value=None):
                                    with patch("app.api.phase3_routes.build_hourly_report", new_callable=AsyncMock) as mock_report:
                                        from app.schemas.market import HourlyReportSchema
                                        from datetime import datetime, timezone

                                        mock_report.return_value = HourlyReportSchema(
                                            timestamp=datetime.now(timezone.utc), assets=[]
                                        )
                                        transport = ASGITransport(app=app)
                                        async with AsyncClient(transport=transport, base_url="http://test") as client:
                                            response = await client.get("/api/v1/dashboard/multi")
                                            assert response.status_code == 200
                                            data = response.json()
                                            assert "assets" in data
                                            assert "BTCUSDT" in data["assets"]
                                            assert data["account"]["mode"] == "demo"
