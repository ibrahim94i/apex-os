"""Shared agent base weights and consensus thresholds."""

from app.schemas.agent import AgentRole, AgentVerdict

AGENT_BASE_WEIGHTS: dict[AgentRole, float] = {
    AgentRole.MARKET_ANALYST: 0.35,
    AgentRole.RISK: 0.40,
    AgentRole.NEWS: 0.25,
}

MIN_WEIGHT_FLOOR_RATIO = 0.50
STRONG_CONSENSUS_THRESHOLD = 0.70


def all_agents_high_confidence(verdicts: list[AgentVerdict]) -> bool:
    """True when all three agents meet or exceed 70% confidence."""
    return len(verdicts) >= 3 and all(
        v.confidence >= STRONG_CONSENSUS_THRESHOLD for v in verdicts
    )


def should_skip_weight_reduction(verdicts: list[AgentVerdict]) -> bool:
    """Strong consensus — never reduce weights for stale/conflict adjustments."""
    return all_agents_high_confidence(verdicts)


def min_weight_floor(agent_id: AgentRole, fallback: float | None = None) -> float:
    """Minimum allowed weight — 50% of the agent's base weight."""
    base = AGENT_BASE_WEIGHTS.get(agent_id, fallback or 0.0)
    return round(base * MIN_WEIGHT_FLOOR_RATIO, 4)


def apply_base_weights_to_verdicts(verdicts: list[AgentVerdict]) -> list[AgentVerdict]:
    """Assign normalized base weights to verdicts (sum = 1.0)."""
    total = sum(AGENT_BASE_WEIGHTS.values())
    weights = {role: round(w / total, 4) for role, w in AGENT_BASE_WEIGHTS.items()}
    return [
        v.model_copy(update={"weight": weights.get(v.agent_id, v.weight)})
        for v in verdicts
    ]
