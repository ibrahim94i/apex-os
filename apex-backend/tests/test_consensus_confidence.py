"""Weighted collective decision confidence tests."""

import pytest

from app.agents.orchestrator import AgentOrchestrator
from app.agents.voting.weighted_engine import AdaptiveWeightedEngine
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.agent import (
    AgentRole,
    AgentVerdict,
    MarketSnapshot,
    TeamDiscussionLLMOutput,
    TeamRoundOpinion,
)
from app.schemas.snapshots import KillSwitchStatusSchema
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_weighted_confidence_formula() -> None:
    """final_confidence = weighted avg of supporting + neutral agent confidences."""
    engine = AdaptiveWeightedEngine()
    verdicts = [
        AgentVerdict(
            agent_id=AgentRole.MARKET_ANALYST,
            agent_name_ar="محلل السوق",
            direction=SignalDirection.LONG,
            confidence=0.70,
            reasoning=["test"],
            weight=0.35,
        ),
        AgentVerdict(
            agent_id=AgentRole.RISK,
            agent_name_ar="وكيل المخاطر",
            direction=SignalDirection.LONG,
            confidence=0.65,
            reasoning=["test"],
            weight=0.40,
        ),
        AgentVerdict(
            agent_id=AgentRole.NEWS,
            agent_name_ar="وكيل الأخبار",
            direction=SignalDirection.LONG,
            confidence=0.50,
            reasoning=["test"],
            weight=0.25,
        ),
    ]
    consensus = await engine.vote("XAUUSD", verdicts)
    expected = 0.70 * 0.35 + 0.65 * 0.40 + 0.50 * 0.25
    assert consensus.final_confidence == pytest.approx(expected, abs=0.001)
    assert consensus.final_confidence == pytest.approx(0.63, abs=0.001)


@pytest.mark.asyncio
async def test_orchestrator_keeps_weighted_confidence_not_round3() -> None:
    """Team discussion round3 must not replace mathematically weighted confidence."""
    now = datetime.now(timezone.utc)
    snapshot = MarketSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        price=2650.0,
        indicators=IndicatorSnapshotSchema(symbol="XAUUSD", timestamp=now, rsi=50.0),
        regime=RegimeSnapshotSchema(
            symbol="XAUUSD",
            timestamp=now,
            regime=RegimeType.TRENDING_UP,
            confidence=0.7,
        ),
        kill_switch=KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE),
        account_balance=10000.0,
        max_risk_pct=1.0,
        max_drawdown_pct=5.0,
    )

    round1 = {
        "market_analyst": TeamRoundOpinion(
            direction=SignalDirection.LONG, confidence=0.70, reasoning=["صاعد"]
        ),
        "risk": TeamRoundOpinion(
            direction=SignalDirection.LONG, confidence=0.65, reasoning=["مقبول"]
        ),
        "news": TeamRoundOpinion(
            direction=SignalDirection.LONG, confidence=0.50, reasoning=["محايد"]
        ),
    }
    team_output = TeamDiscussionLLMOutput(
        round1_initial=round1,
        round2_responses=round1,
        round3_final=TeamRoundOpinion(
            direction=SignalDirection.LONG,
            confidence=0.70,
            reasoning=["قرار نهائي LLM"],
        ),
        agreements=["اتفاق على الشراء"],
        disagreements=[],
        discussion_summary=["ملخص النقاش"],
    )

    mock_verdicts = [
        AgentVerdict(
            agent_id=AgentRole.MARKET_ANALYST,
            agent_name_ar="محلل السوق",
            direction=SignalDirection.LONG,
            confidence=0.70,
            reasoning=["صاعد"],
            weight=0.35,
            used_llm=True,
        ),
        AgentVerdict(
            agent_id=AgentRole.RISK,
            agent_name_ar="وكيل المخاطر",
            direction=SignalDirection.LONG,
            confidence=0.65,
            reasoning=["مقبول"],
            weight=0.40,
            used_llm=True,
        ),
        AgentVerdict(
            agent_id=AgentRole.NEWS,
            agent_name_ar="وكيل الأخبار",
            direction=SignalDirection.LONG,
            confidence=0.50,
            reasoning=["محايد"],
            weight=0.25,
            used_llm=True,
        ),
    ]

    h1_verdicts = mock_verdicts[:2]
    news_verdict = mock_verdicts[2]

    orchestrator = AgentOrchestrator()
    with patch.object(
        orchestrator.team_service,
        "analyze_h1",
        new=AsyncMock(return_value=(h1_verdicts, True, None, team_output, "openai")),
    ), patch(
        "app.agents.orchestrator.get_cached_consensus",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.agents.orchestrator.get_news_verdict",
        new=AsyncMock(return_value=news_verdict.model_dump(mode="json")),
    ), patch(
        "app.agents.orchestrator.set_cached_consensus",
        new=AsyncMock(),
    ):
        consensus = await orchestrator.run(snapshot)

    assert consensus.final_confidence == pytest.approx(0.63, abs=0.001)
    assert consensus.final_confidence != pytest.approx(0.70, abs=0.001)
    assert consensus.team_discussion is not None
    assert consensus.team_discussion.round3_final.confidence == 0.70
