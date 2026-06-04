"""Display-time fixes for cached agent consensus."""

from __future__ import annotations

import re

from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict

_BALANCE_LINE = re.compile(r"^رصيد الحساب:\s*\$")


def patch_consensus_account_balance(
    consensus: AgentConsensus, balance: float
) -> AgentConsensus:
    """Replace stale risk-agent balance lines with the live account balance."""
    balance_line = f"رصيد الحساب: ${balance:,.0f}"
    verdicts: list[AgentVerdict] = []

    for verdict in consensus.verdicts:
        if verdict.agent_id != AgentRole.RISK:
            verdicts.append(verdict)
            continue

        patched = False
        reasoning: list[str] = []
        for line in verdict.reasoning:
            if _BALANCE_LINE.match(line):
                reasoning.append(balance_line)
                patched = True
            else:
                reasoning.append(line)
        if not patched:
            reasoning.insert(0, balance_line)

        verdicts.append(verdict.model_copy(update={"reasoning": reasoning}))

    return consensus.model_copy(update={"verdicts": verdicts})
