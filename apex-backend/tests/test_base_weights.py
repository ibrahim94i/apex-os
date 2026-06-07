"""Tests for agent base weights and strong consensus rules."""

import pytest

from app.agents.base_weights import (
    AGENT_BASE_WEIGHTS,
    all_agents_high_confidence,
    min_weight_floor,
)
from app.agents.voting.weighted_engine import AdaptiveWeightedEngine
from app.schemas import SignalDirection
from app.schemas.agent import AgentRole, AgentVerdict


def _three_verdicts(**confidences: float) -> list[AgentVerdict]:
    defaults = {
        AgentRole.MARKET_ANALYST: 0.80,
        AgentRole.RISK: 0.75,
        AgentRole.NEWS: 0.72,
    }
    defaults.update(confidences)
    names = {
        AgentRole.MARKET_ANALYST: "محلل",
        AgentRole.RISK: "مخاطr",
        AgentRole.NEWS: "أخبار",
    }
    return [
        AgentVerdict(
            agent_id=role,
            agent_name_ar=names[role],
            direction=SignalDirection.LONG,
            confidence=conf,
            reasoning=["test"],
            weight=AGENT_BASE_WEIGHTS[role],
        )
        for role, conf in defaults.items()
    ]


@pytest.mark.asyncio
async def test_all_agents_high_confidence_uses_base_weights() -> None:
    engine = AdaptiveWeightedEngine()
    verdicts = _three_verdicts()
    weights = await engine.compute_weights(None, "BTCUSDT", "TRENDING_UP", verdicts)
    assert weights[AgentRole.MARKET_ANALYST] == pytest.approx(0.35, abs=0.001)
    assert weights[AgentRole.RISK] == pytest.approx(0.40, abs=0.001)
    assert weights[AgentRole.NEWS] == pytest.approx(0.25, abs=0.001)


def test_all_agents_high_confidence_requires_three_agents() -> None:
    verdicts = _three_verdicts()
    assert all_agents_high_confidence(verdicts) is True
    verdicts[2] = verdicts[2].model_copy(update={"confidence": 0.70})
    assert all_agents_high_confidence(verdicts) is False


def test_min_weight_floor_is_half_of_base() -> None:
    assert min_weight_floor(AgentRole.NEWS, 0.25) == pytest.approx(0.125)
    assert min_weight_floor(AgentRole.MARKET_ANALYST, 0.35) == pytest.approx(0.175)
