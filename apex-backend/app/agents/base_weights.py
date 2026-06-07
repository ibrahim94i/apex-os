"""Shared agent base weights and consensus thresholds."""

from app.schemas.agent import AgentRole

AGENT_BASE_WEIGHTS: dict[AgentRole, float] = {
    AgentRole.MARKET_ANALYST: 0.35,
    AgentRole.RISK: 0.40,
    AgentRole.NEWS: 0.25,
}

MIN_WEIGHT_FLOOR_RATIO = 0.50
STRONG_CONSENSUS_THRESHOLD = 0.70


def all_agents_high_confidence(verdicts) -> bool:
    """True when every agent confidence exceeds 70%."""
    return len(verdicts) >= 3 and all(v.confidence > STRONG_CONSENSUS_THRESHOLD for v in verdicts)


def min_weight_floor(agent_id: AgentRole, fallback: float) -> float:
    base = AGENT_BASE_WEIGHTS.get(agent_id, fallback)
    return round(base * MIN_WEIGHT_FLOOR_RATIO, 4)
