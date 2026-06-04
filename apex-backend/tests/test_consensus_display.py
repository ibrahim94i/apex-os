"""Tests for consensus balance display patching."""

from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict, SignalDirection
from app.services.consensus_display import patch_consensus_account_balance
from datetime import datetime, timezone


def _consensus_with_risk_balance(balance_line: str) -> AgentConsensus:
    return AgentConsensus(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        final_direction=SignalDirection.NEUTRAL,
        final_confidence=0.5,
        verdicts=[
            AgentVerdict(
                agent_id=AgentRole.RISK,
                agent_name_ar="وكيل المخاطر",
                direction=SignalDirection.NEUTRAL,
                confidence=0.7,
                reasoning=[balance_line, "الحد الأقصى للمخاطرة: 1.0% لكل صفقة"],
                weight=0.35,
            )
        ],
        vote_scores={},
    )


def test_patch_replaces_stale_demo_balance() -> None:
    consensus = _consensus_with_risk_balance("رصيد الحساب: $100")
    patched = patch_consensus_account_balance(consensus, 10_000.0)
    risk = next(v for v in patched.verdicts if v.agent_id == AgentRole.RISK)
    assert any("10,000" in line for line in risk.reasoning)
    assert not any("$100" in line and "10,000" not in line for line in risk.reasoning)


def test_patch_inserts_balance_when_missing() -> None:
    consensus = AgentConsensus(
        symbol="EURUSD",
        timestamp=datetime.now(timezone.utc),
        final_direction=SignalDirection.NEUTRAL,
        final_confidence=0.5,
        verdicts=[
            AgentVerdict(
                agent_id=AgentRole.RISK,
                agent_name_ar="وكيل المخاطر",
                direction=SignalDirection.NEUTRAL,
                confidence=0.7,
                reasoning=["الحد الأقصى للمخاطرة: 1.0% لكل صفقة"],
                weight=0.35,
            )
        ],
        vote_scores={},
    )
    patched = patch_consensus_account_balance(consensus, 250.0)
    risk = next(v for v in patched.verdicts if v.agent_id == AgentRole.RISK)
    assert risk.reasoning[0] == "رصيد الحساب: $250"
