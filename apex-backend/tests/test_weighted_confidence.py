"""Weighted collective confidence — formula accuracy across all assets."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.voting.weighted_engine import (
    AdaptiveWeightedEngine,
    compute_direction_normalized,
    compute_weighted_confidence,
    direction_from_normalized,
)
from app.schemas import SignalDirection
from app.schemas.agent import AgentRole, AgentVerdict

ACTIVE_SYMBOLS = ["XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "BTCUSDT"]


def _verdicts(
    *,
    market_dir: SignalDirection = SignalDirection.LONG,
    market_conf: float = 0.72,
    market_w: float = 0.35,
    risk_dir: SignalDirection = SignalDirection.LONG,
    risk_conf: float = 0.80,
    risk_w: float = 0.50,
    news_dir: SignalDirection = SignalDirection.LONG,
    news_conf: float = 0.60,
    news_w: float = 0.15,
) -> list[AgentVerdict]:
    return [
        AgentVerdict(
            agent_id=AgentRole.MARKET_ANALYST,
            agent_name_ar="محلل السوق",
            direction=market_dir,
            confidence=market_conf,
            reasoning=["test"],
            weight=market_w,
        ),
        AgentVerdict(
            agent_id=AgentRole.RISK,
            agent_name_ar="وkiel المخاطr",
            direction=risk_dir,
            confidence=risk_conf,
            reasoning=["test"],
            weight=risk_w,
        ),
        AgentVerdict(
            agent_id=AgentRole.NEWS,
            agent_name_ar="وkiel الأخبار",
            direction=news_dir,
            confidence=news_conf,
            reasoning=["test"],
            weight=news_w,
        ),
    ]


def _expected_confidence(verdicts: list[AgentVerdict], final_direction: SignalDirection) -> float:
    confidence_sum = 0.0
    weight_sum = 0.0
    for verdict in verdicts:
        if verdict.direction in (final_direction, SignalDirection.NEUTRAL):
            confidence_sum += verdict.confidence * verdict.weight
            weight_sum += verdict.weight
    return confidence_sum / weight_sum if weight_sum else 0.0


def test_gold_manual_example_all_long() -> None:
    verdicts = _verdicts()
    expected = 0.72 * 0.35 + 0.80 * 0.50 + 0.60 * 0.15
    assert expected == pytest.approx(0.742, abs=0.0001)
    assert compute_weighted_confidence(verdicts, SignalDirection.LONG) == pytest.approx(0.742, abs=0.0001)


def test_gold_manual_example_news_neutral_not_diluted() -> None:
    """Regression: NEUTRAL news must not drag confidence down to ~65%."""
    verdicts = _verdicts(news_dir=SignalDirection.NEUTRAL)
    assert compute_weighted_confidence(verdicts, SignalDirection.LONG) == pytest.approx(0.742, abs=0.0001)
    assert compute_direction_normalized(verdicts) == pytest.approx(0.652, abs=0.0001)


@pytest.mark.parametrize("symbol", ACTIVE_SYMBOLS)
def test_confidence_independent_of_symbol(symbol: str) -> None:
    verdicts = _verdicts()
    assert compute_weighted_confidence(verdicts, SignalDirection.LONG) == pytest.approx(0.742, abs=0.0001)


@pytest.mark.parametrize(
    ("market_dir", "risk_dir", "news_dir", "expected_dir"),
    [
        (SignalDirection.LONG, SignalDirection.LONG, SignalDirection.LONG, SignalDirection.LONG),
        (SignalDirection.SHORT, SignalDirection.SHORT, SignalDirection.SHORT, SignalDirection.SHORT),
        (SignalDirection.LONG, SignalDirection.SHORT, SignalDirection.NEUTRAL, SignalDirection.NEUTRAL),
        (SignalDirection.LONG, SignalDirection.LONG, SignalDirection.SHORT, SignalDirection.LONG),
    ],
)
def test_direction_from_normalized_cases(
    market_dir: SignalDirection,
    risk_dir: SignalDirection,
    news_dir: SignalDirection,
    expected_dir: SignalDirection,
) -> None:
    verdicts = _verdicts(
        market_dir=market_dir,
        risk_dir=risk_dir,
        news_dir=news_dir,
        market_w=0.35,
        risk_w=0.40,
        news_w=0.25,
        market_conf=0.80,
        risk_conf=0.70,
        news_conf=0.60,
    )
    normalized = compute_direction_normalized(verdicts)
    assert direction_from_normalized(normalized) == expected_dir
    if expected_dir == SignalDirection.NEUTRAL:
        assert compute_weighted_confidence(verdicts, expected_dir) == pytest.approx(
            abs(normalized),
            abs=0.0001,
        )
    else:
        assert compute_weighted_confidence(verdicts, expected_dir) == pytest.approx(
            _expected_confidence(verdicts, expected_dir),
            abs=0.0001,
        )


def test_opposing_agent_excluded_from_confidence() -> None:
    verdicts = _verdicts(
        market_dir=SignalDirection.LONG,
        market_conf=0.90,
        market_w=0.35,
        risk_dir=SignalDirection.SHORT,
        risk_conf=0.90,
        risk_w=0.40,
        news_dir=SignalDirection.NEUTRAL,
        news_conf=0.60,
        news_w=0.25,
    )
    final = direction_from_normalized(compute_direction_normalized(verdicts))
    assert final == SignalDirection.NEUTRAL
    assert compute_weighted_confidence(verdicts, SignalDirection.LONG) == pytest.approx(
        (0.90 * 0.35 + 0.60 * 0.25) / (0.35 + 0.25),
        abs=0.0001,
    )


def test_short_confidence_uses_supporting_agents_only() -> None:
    verdicts = _verdicts(
        market_dir=SignalDirection.SHORT,
        market_conf=0.75,
        market_w=0.35,
        risk_dir=SignalDirection.SHORT,
        risk_conf=0.85,
        risk_w=0.40,
        news_dir=SignalDirection.NEUTRAL,
        news_conf=0.55,
        news_w=0.25,
    )
    final = direction_from_normalized(compute_direction_normalized(verdicts))
    assert final == SignalDirection.SHORT
    expected = (0.75 * 0.35 + 0.85 * 0.40 + 0.55 * 0.25) / 1.0
    assert compute_weighted_confidence(verdicts, final) == pytest.approx(expected, abs=0.0001)


def test_base_weights_all_long() -> None:
    verdicts = _verdicts(
        market_w=0.35,
        risk_w=0.40,
        news_w=0.25,
        market_conf=0.70,
        risk_conf=0.65,
        news_conf=0.50,
    )
    expected = 0.70 * 0.35 + 0.65 * 0.40 + 0.50 * 0.25
    assert compute_weighted_confidence(verdicts, SignalDirection.LONG) == pytest.approx(expected, abs=0.0001)


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ACTIVE_SYMBOLS)
async def test_vote_matches_formula_for_gold_like_case(symbol: str) -> None:
    engine = AdaptiveWeightedEngine()
    verdicts = _verdicts(news_dir=SignalDirection.NEUTRAL)

    with patch.object(
        engine,
        "compute_weights",
        new=AsyncMock(
            return_value={
                AgentRole.MARKET_ANALYST: 0.35,
                AgentRole.RISK: 0.50,
                AgentRole.NEWS: 0.15,
            }
        ),
    ), patch(
        "app.services.agent_freshness.apply_dynamic_weight_adjustments",
        return_value=(verdicts, []),
    ):
        consensus = await engine.vote(symbol, verdicts)

    assert consensus.final_direction == SignalDirection.LONG
    assert consensus.final_confidence == pytest.approx(0.742, abs=0.0001)


@pytest.mark.asyncio
async def test_vote_with_adaptive_weights_from_memory() -> None:
    engine = AdaptiveWeightedEngine()
    verdicts = _verdicts(news_conf=0.60, news_dir=SignalDirection.LONG)

    mock_session = AsyncMock()
    with patch(
        "app.agents.voting.weighted_engine.memory_engine.get_agent_accuracy",
        new=AsyncMock(side_effect=[0.65, 0.40]),
    ), patch.object(engine, "_log_weights", new=AsyncMock()), patch(
        "app.services.agent_freshness.apply_dynamic_weight_adjustments",
        side_effect=lambda v, *_: (v, []),
    ):
        consensus = await engine.vote(
            "XAUUSD",
            verdicts,
            regime="TRENDING_UP",
            session=mock_session,
            snapshot=None,
        )

    assert verdicts[0].weight == pytest.approx(0.35, abs=0.001)
    assert verdicts[1].weight == pytest.approx(0.50, abs=0.001)
    assert verdicts[2].weight == pytest.approx(0.15, abs=0.001)
    assert consensus.final_confidence == pytest.approx(0.742, abs=0.001)
