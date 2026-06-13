"""Orchestrator news agent merge tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.orchestrator import AgentOrchestrator
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.agent import AgentRole, AgentVerdict, MarketSnapshot
from app.schemas.snapshots import KillSwitchStatusSchema


def _snapshot() -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    return MarketSnapshot(
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


def _news_verdict() -> AgentVerdict:
    return AgentVerdict(
        agent_id=AgentRole.NEWS,
        agent_name_ar="وكيل الأخبار",
        direction=SignalDirection.NEUTRAL,
        confidence=0.55,
        reasoning=["اختبار الأخبار"],
        weight=0.25,
        used_llm=True,
    )


@pytest.mark.asyncio
async def test_orchestrator_runs_news_agent_when_cache_empty() -> None:
    snapshot = _snapshot()
    h1_verdicts = [
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
    ]
    news = _news_verdict()
    orchestrator = AgentOrchestrator()

    with patch(
        "app.agents.orchestrator.get_cached_consensus",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.agents.orchestrator.get_news_verdict",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.agents.orchestrator.set_news_verdict",
        new=AsyncMock(),
    ) as mock_set_news, patch(
        "app.agents.orchestrator.set_cached_consensus",
        new=AsyncMock(),
    ), patch.object(
        orchestrator.team_service,
        "analyze_h1",
        new=AsyncMock(return_value=(h1_verdicts, True, None, None, "openai")),
    ), patch(
        "app.agents.news.agent.NewsAgent",
    ) as mock_news_cls:
        mock_news_cls.return_value.analyze = AsyncMock(return_value=news)
        consensus = await orchestrator.run_h1(snapshot)

    assert len(consensus.verdicts) == 3
    assert any(v.agent_id == AgentRole.NEWS for v in consensus.verdicts)
    mock_set_news.assert_awaited_once()


@pytest.mark.asyncio
async def test_news_monitor_runs_when_market_closed_for_testing() -> None:
    from app.services.news_monitor_service import run_news_monitor_for_symbol

    with patch("app.services.news_monitor_service.settings.agents_run_when_market_closed", True):
        with patch("app.services.news_monitor_service.is_market_open", return_value=False):
            with patch(
                "app.services.news_monitor_service._serve_stale_if_llm_blocked",
                new=AsyncMock(return_value=None),
            ):
                with patch(
                    "app.services.news_monitor_service._load_market_context",
                    new=AsyncMock(return_value=None),
                ) as mock_ctx:
                    await run_news_monitor_for_symbol("XAUUSD")
    mock_ctx.assert_awaited_once()
