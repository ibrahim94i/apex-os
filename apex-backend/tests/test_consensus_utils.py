"""Consensus completeness helpers."""

from datetime import datetime, timezone

from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict
from app.schemas.snapshots import KillSwitchStatusSchema
from app.services.consensus_utils import (
    consensus_has_all_agents,
    consensus_has_h1_agents,
    extract_h1_verdicts,
)


def _consensus(*roles: AgentRole) -> AgentConsensus:
    now = datetime.now(timezone.utc)
    verdicts = []
    mapping = {
        AgentRole.MARKET_ANALYST: ("محلل السوق", 0.35),
        AgentRole.RISK: ("وكيل المخاطر", 0.40),
        AgentRole.NEWS: ("وكيل الأخبار", 0.25),
    }
    for role in roles:
        name, weight = mapping[role]
        verdicts.append(
            AgentVerdict(
                agent_id=role,
                agent_name_ar=name,
                direction=SignalDirection.NEUTRAL,
                confidence=0.5,
                reasoning=["test"],
                weight=weight,
                used_llm=True,
            )
        )
    return AgentConsensus(
        symbol="XAUUSD",
        timestamp=now,
        final_direction=SignalDirection.NEUTRAL,
        final_confidence=0.5,
        verdicts=verdicts,
        vote_scores={},
    )


def test_extract_h1_verdicts() -> None:
    consensus = _consensus(AgentRole.MARKET_ANALYST, AgentRole.RISK, AgentRole.NEWS)
    h1 = extract_h1_verdicts(consensus)
    assert len(h1) == 2
    assert {v.agent_id for v in h1} == {AgentRole.MARKET_ANALYST, AgentRole.RISK}


def test_news_only_consensus_missing_h1_agents() -> None:
    consensus = _consensus(AgentRole.NEWS)
    assert consensus_has_h1_agents(consensus) is False
    assert consensus_has_all_agents(consensus) is False
