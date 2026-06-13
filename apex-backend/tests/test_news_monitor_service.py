"""Tests for news monitor consensus refresh."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict, MarketSnapshot
from app.schemas.snapshots import KillSwitchStatusSchema
from app.services.news_monitor_service import _refresh_consensus_with_news


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
        reasoning=["test"],
        weight=0.25,
        used_llm=True,
    )


def _full_consensus() -> AgentConsensus:
    now = datetime.now(timezone.utc)
    return AgentConsensus(
        symbol="XAUUSD",
        timestamp=now,
        final_direction=SignalDirection.LONG,
        final_confidence=0.7,
        verdicts=[
            AgentVerdict(
                agent_id=AgentRole.MARKET_ANALYST,
                agent_name_ar="محلل السوق",
                direction=SignalDirection.LONG,
                confidence=0.7,
                reasoning=["up"],
                weight=0.35,
                used_llm=True,
            ),
            AgentVerdict(
                agent_id=AgentRole.RISK,
                agent_name_ar="وكيل المخاطر",
                direction=SignalDirection.LONG,
                confidence=0.65,
                reasoning=["ok"],
                weight=0.40,
                used_llm=True,
            ),
            _news_verdict(),
        ],
        vote_scores={},
    )


@pytest.mark.asyncio
async def test_news_refresh_without_h1_does_not_overwrite_consensus() -> None:
    news = _news_verdict()
    with patch(
        "app.services.news_monitor_service._resolve_h1_verdicts",
        new=AsyncMock(return_value=([], None, None)),
    ):
        with patch(
            "app.services.news_monitor_service.set_news_verdict",
            new=AsyncMock(),
        ) as mock_set_news:
            with patch(
                "app.services.news_monitor_service.set_agent_consensus",
                new=AsyncMock(),
            ) as mock_set_consensus:
                with patch(
                    "app.services.news_monitor_service.broadcaster.broadcast_agent_consensus",
                    new=AsyncMock(),
                ) as mock_broadcast:
                    await _refresh_consensus_with_news("XAUUSD", news, _snapshot())

    mock_set_news.assert_awaited_once()
    mock_set_consensus.assert_not_awaited()
    mock_broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_news_refresh_merges_three_verdicts_when_h1_present() -> None:
    news = _news_verdict()
    full = _full_consensus()
    h1 = full.verdicts[:2]

    async def fake_vote(symbol, verdicts, **kwargs):
        assert len(verdicts) == 3
        return full.model_copy(update={"verdicts": verdicts})

    with patch(
        "app.services.news_monitor_service._resolve_h1_verdicts",
        new=AsyncMock(return_value=(h1, None, "openai")),
    ):
        with patch(
            "app.services.news_monitor_service.get_agent_consensus",
            new=AsyncMock(return_value=full.model_dump(mode="json")),
        ):
            with patch(
                "app.services.news_monitor_service._voting_engine.vote",
                new=AsyncMock(side_effect=fake_vote),
            ):
                with patch(
                    "app.services.news_monitor_service.set_agent_consensus",
                    new=AsyncMock(),
                ) as mock_set_consensus:
                    with patch(
                        "app.services.news_monitor_service.broadcaster.broadcast_agent_consensus",
                        new=AsyncMock(),
                    ):
                        await _refresh_consensus_with_news("XAUUSD", news, _snapshot())

    mock_set_consensus.assert_awaited_once()
