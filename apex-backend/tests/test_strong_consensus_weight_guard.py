"""Strong consensus must preserve base weights even with indicator conflict."""

from datetime import datetime, timezone

import pytest

from app.agents.voting.weighted_engine import AdaptiveWeightedEngine
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.agent import AgentRole, AgentVerdict, MarketSnapshot
from app.schemas.snapshots import KillSwitchStatusSchema


def _snapshot(indicators: IndicatorSnapshotSchema) -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    return MarketSnapshot(
        symbol="USDJPY",
        timestamp=now,
        price=150.0,
        indicators=indicators,
        regime=RegimeSnapshotSchema(
            symbol="USDJPY",
            timestamp=now,
            regime=RegimeType.TRENDING_UP,
            confidence=0.8,
        ),
        kill_switch=KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE),
        account_balance=10000.0,
        max_risk_pct=1.0,
        max_drawdown_pct=5.0,
        feed_stale=False,
    )


def _high_confidence_long_verdicts() -> list[AgentVerdict]:
    return [
        AgentVerdict(
            agent_id=AgentRole.MARKET_ANALYST,
            agent_name_ar="محلل السوق",
            direction=SignalDirection.LONG,
            confidence=0.89,
            reasoning=["test"],
            weight=0.35,
        ),
        AgentVerdict(
            agent_id=AgentRole.RISK,
            agent_name_ar="وkiel المخاطr",
            direction=SignalDirection.LONG,
            confidence=0.88,
            reasoning=["test"],
            weight=0.40,
        ),
        AgentVerdict(
            agent_id=AgentRole.NEWS,
            agent_name_ar="وkiel الأخبار",
            direction=SignalDirection.LONG,
            confidence=0.90,
            reasoning=["test"],
            weight=0.25,
        ),
    ]


@pytest.mark.asyncio
async def test_strong_consensus_keeps_base_weights_despite_indicator_conflict() -> None:
    """Regression: 89% agents must not drop to 0% via weight slashing."""
    now = datetime.now(timezone.utc)
    indicators = IndicatorSnapshotSchema(
        symbol="USDJPY",
        timestamp=now,
        rsi=75.0,
        macd=-1.0,
        macd_signal=0.5,
        ema_50=149.0,
        ema_200=151.0,
    )
    verdicts = _high_confidence_long_verdicts()
    engine = AdaptiveWeightedEngine()

    consensus = await engine.vote(
        "USDJPY",
        verdicts,
        regime="TRENDING_UP",
        session=None,
        snapshot=_snapshot(indicators),
    )

    assert consensus.verdicts[0].weight == pytest.approx(0.35, abs=0.001)
    assert consensus.verdicts[1].weight == pytest.approx(0.40, abs=0.001)
    assert consensus.verdicts[2].weight == pytest.approx(0.25, abs=0.001)
    assert consensus.final_direction == SignalDirection.LONG
    assert consensus.final_confidence == pytest.approx(0.89, abs=0.01)
    assert not any("indicator conflict" in line for line in consensus.reasoning_summary)
