"""End-to-end tests for multi-agent system."""

from datetime import datetime, timezone

import pytest

from app.agents.orchestrator import AgentOrchestrator
from app.agents.voting_engine import WeightedVotingEngine
from app.schemas import (
    IndicatorSnapshotSchema,
    KillSwitchStatus,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
    RegimeType,
    SignalDirection,
)
from app.schemas.agent import AgentRole, AgentVerdict, MarketSnapshot
from app.services.market_snapshot import build_market_snapshot
from app.utils.llm_client import LLMClient


def _sample_snapshot(symbol: str = "BTCUSDT", kill_active: bool = False) -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    if symbol == "EURUSD":
        price = 1.08500
        indicators = IndicatorSnapshotSchema(
            symbol=symbol,
            timestamp=now,
            rsi=48.0,
            macd=0.0002,
            macd_signal=0.0001,
            ema_9=1.08520,
            ema_21=1.08480,
            ema_50=1.08400,
            ema_200=1.08300,
            atr=0.0012,
            adx=28.0,
        )
    elif symbol == "XAUUSD":
        price = 2700.0
        indicators = IndicatorSnapshotSchema(
            symbol=symbol,
            timestamp=now,
            rsi=28.0,
            macd=5.0,
            macd_signal=3.0,
            ema_9=2705.0,
            ema_21=2695.0,
            ema_50=2680.0,
            ema_200=2650.0,
            atr=8.0,
            adx=32.0,
        )
    else:
        price = 95000.0
        indicators = IndicatorSnapshotSchema(
            symbol=symbol,
            timestamp=now,
            rsi=28.0,
            macd=150.0,
            macd_signal=100.0,
            ema_9=95100.0,
            ema_21=94800.0,
            ema_50=94000.0,
            atr=500.0,
            adx=32.0,
        )
    return MarketSnapshot(
        symbol=symbol,
        timestamp=now,
        price=price,
        indicators=indicators,
        regime=RegimeSnapshotSchema(
            symbol=symbol,
            timestamp=now,
            regime=RegimeType.TRENDING_UP,
            confidence=0.75,
            adx_value=32.0,
            volatility_pct=0.8,
        ),
        kill_switch=KillSwitchStatusSchema(
            status=KillSwitchStatus.ACTIVE if kill_active else KillSwitchStatus.INACTIVE,
            reason="Test" if kill_active else None,
        ),
        account_balance=10000.0,
        max_risk_pct=1.5,
        max_drawdown_pct=5.0,
    )


@pytest.mark.asyncio
async def test_market_analyst_agent_rule_based() -> None:
    from app.agents.market_analyst.agent import MarketAnalystAgent

    agent = MarketAnalystAgent(client=LLMClient(api_key=""))
    verdict = await agent.analyze(_sample_snapshot())
    assert verdict.agent_id == AgentRole.MARKET_ANALYST
    assert verdict.direction in (SignalDirection.LONG, SignalDirection.SHORT, SignalDirection.NEUTRAL)
    assert len(verdict.reasoning) >= 1
    assert verdict.agent_name_ar == "محلل السوق"


@pytest.mark.asyncio
async def test_risk_agent_blocks_on_kill_switch() -> None:
    from app.agents.risk.agent import RiskAgent

    agent = RiskAgent(client=LLMClient(api_key=""))
    verdict = await agent.analyze(_sample_snapshot(kill_active=True))
    assert verdict.direction == SignalDirection.NEUTRAL
    assert any("مفتاح" in r for r in verdict.reasoning)


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["BTCUSDT", "XAUUSD", "EURUSD"])
async def test_orchestrator_all_assets(symbol: str) -> None:
    orchestrator = AgentOrchestrator()
    consensus = await orchestrator.run(_sample_snapshot(symbol))
    assert consensus.symbol == symbol
    assert len(consensus.verdicts) == 3
    assert consensus.final_direction in (
        SignalDirection.LONG,
        SignalDirection.SHORT,
        SignalDirection.NEUTRAL,
    )
    assert 0 <= consensus.final_confidence <= 1


@pytest.mark.asyncio
async def test_orchestrator_produces_consensus() -> None:
    orchestrator = AgentOrchestrator()
    consensus = await orchestrator.run(_sample_snapshot("BTCUSDT"))
    assert consensus.symbol == "BTCUSDT"
    assert len(consensus.verdicts) == 3
    assert consensus.final_direction in (
        SignalDirection.LONG,
        SignalDirection.SHORT,
        SignalDirection.NEUTRAL,
    )
    assert 0 <= consensus.final_confidence <= 1


@pytest.mark.asyncio
async def test_voting_engine_weighted_scores() -> None:
    engine = WeightedVotingEngine()
    verdicts = [
        AgentVerdict(
            agent_id=AgentRole.MARKET_ANALYST,
            agent_name_ar="محلل السوق",
            direction=SignalDirection.LONG,
            confidence=0.8,
            reasoning=["test"],
            weight=0.4,
        ),
        AgentVerdict(
            agent_id=AgentRole.RISK,
            agent_name_ar="وكيل المخاطر",
            direction=SignalDirection.LONG,
            confidence=0.7,
            reasoning=["test"],
            weight=0.35,
        ),
        AgentVerdict(
            agent_id=AgentRole.NEWS,
            agent_name_ar="وكيل الأخبار",
            direction=SignalDirection.NEUTRAL,
            confidence=0.5,
            reasoning=["test"],
            weight=0.25,
        ),
    ]
    consensus = await engine.vote("BTCUSDT", verdicts)
    assert consensus.final_direction == SignalDirection.LONG
    assert "market_analyst" in consensus.vote_scores


@pytest.mark.asyncio
async def test_market_snapshot_builder() -> None:
    now = datetime.now(timezone.utc)
    indicators = IndicatorSnapshotSchema(symbol="BTCUSDT", timestamp=now, rsi=50.0)
    regime = RegimeSnapshotSchema(
        symbol="BTCUSDT", timestamp=now, regime=RegimeType.RANGING, confidence=0.5
    )
    ks = KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE)
    snapshot = await build_market_snapshot("BTCUSDT", 95000.0, indicators, regime, ks)
    assert snapshot.price == 95000.0
    assert snapshot.symbol == "BTCUSDT"


@pytest.mark.asyncio
async def test_agents_api_endpoint() -> None:
    from unittest.mock import AsyncMock, patch

    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.schemas.agent import AgentConsensus

    mock_consensus = AgentConsensus(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        final_direction=SignalDirection.LONG,
        final_confidence=0.7,
        verdicts=[],
        vote_scores={},
    )

    with patch(
        "app.api.routes.get_agent_consensus",
        new_callable=AsyncMock,
        return_value=mock_consensus.model_dump(mode="json"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/agents/consensus?symbol=BTCUSDT")
            assert response.status_code == 200
            data = response.json()
            assert data["final_direction"] == "LONG"
