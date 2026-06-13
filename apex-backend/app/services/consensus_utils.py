"""Helpers for validating agent consensus completeness."""

from __future__ import annotations

from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict


def extract_h1_verdicts(consensus: AgentConsensus) -> list[AgentVerdict]:
    """Market analyst + risk verdicts only."""
    return [
        verdict
        for verdict in consensus.verdicts
        if verdict.agent_id in (AgentRole.MARKET_ANALYST, AgentRole.RISK)
    ]


def consensus_has_h1_agents(consensus: AgentConsensus) -> bool:
    """True when both market analyst and risk agent are present."""
    roles = {verdict.agent_id for verdict in consensus.verdicts}
    return AgentRole.MARKET_ANALYST in roles and AgentRole.RISK in roles


def consensus_has_all_agents(consensus: AgentConsensus) -> bool:
    """True when market, risk, and news agents are all present."""
    roles = {verdict.agent_id for verdict in consensus.verdicts}
    return (
        AgentRole.MARKET_ANALYST in roles
        and AgentRole.RISK in roles
        and AgentRole.NEWS in roles
    )
