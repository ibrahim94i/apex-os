"""Adaptive weighted voting engine with risk agent veto."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_weights import (
    AGENT_BASE_WEIGHTS,
    MIN_WEIGHT_FLOOR_RATIO,
    all_agents_high_confidence,
    min_weight_floor,
)
from app.models.phase3 import AgentWeightLog
from app.schemas import SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict
from app.services.memory_engine import memory_engine

RISK_MIN_WEIGHT = 0.40
MARKET_BASE = 0.35
NEWS_BASE = 0.25
DIRECTION_VALUES = {
    SignalDirection.LONG: 1.0,
    SignalDirection.SHORT: -1.0,
    SignalDirection.NEUTRAL: 0.0,
}
DIRECTION_THRESHOLD = 0.15


def compute_direction_normalized(verdicts: list[AgentVerdict]) -> float:
    """Signed score for direction: Σ(sign × confidence × weight) / Σ(weight)."""
    weighted_sum = 0.0
    total_weight = 0.0
    for verdict in verdicts:
        direction_val = DIRECTION_VALUES[verdict.direction]
        weighted_sum += direction_val * verdict.confidence * verdict.weight
        total_weight += verdict.weight
    return weighted_sum / total_weight if total_weight else 0.0


def direction_from_normalized(normalized: float) -> SignalDirection:
    if normalized > DIRECTION_THRESHOLD:
        return SignalDirection.LONG
    if normalized < -DIRECTION_THRESHOLD:
        return SignalDirection.SHORT
    return SignalDirection.NEUTRAL


def compute_weighted_confidence(
    verdicts: list[AgentVerdict],
    final_direction: SignalDirection,
) -> float:
    """
    Weighted confidence among agents aligned with the final direction.
    Supporting + NEUTRAL agents contribute confidence × weight; opposing agents are excluded.
    """
    if final_direction == SignalDirection.NEUTRAL:
        return min(abs(compute_direction_normalized(verdicts)), 1.0)

    confidence_sum = 0.0
    weight_sum = 0.0
    for verdict in verdicts:
        if verdict.direction in (final_direction, SignalDirection.NEUTRAL):
            confidence_sum += verdict.confidence * verdict.weight
            weight_sum += verdict.weight

    if weight_sum <= 0:
        return 0.0
    return min(confidence_sum / weight_sum, 1.0)


def compute_vote_scores(verdicts: list[AgentVerdict]) -> dict[str, float]:
    return {
        verdict.agent_id.value: round(
            DIRECTION_VALUES[verdict.direction] * verdict.confidence * verdict.weight,
            4,
        )
        for verdict in verdicts
    }


class AdaptiveWeightedEngine:
    DIRECTION_VALUES = DIRECTION_VALUES

    async def compute_weights(
        self,
        session: AsyncSession | None,
        symbol: str,
        regime: str,
        verdicts: list[AgentVerdict],
    ) -> dict[AgentRole, float]:
        if all_agents_high_confidence(verdicts):
            total = sum(AGENT_BASE_WEIGHTS.values())
            weights = {
                role: round(w / total, 4) for role, w in AGENT_BASE_WEIGHTS.items()
            }
            for v in verdicts:
                v.weight = weights.get(v.agent_id, v.weight)
            return weights

        market_acc = 0.5
        news_acc = 0.5

        if session:
            market_acc = await memory_engine.get_agent_accuracy(
                session, symbol, regime, AgentRole.MARKET_ANALYST.value
            )
            news_acc = await memory_engine.get_agent_accuracy(
                session, symbol, regime, AgentRole.NEWS.value
            )

        market_w = MARKET_BASE
        news_w = NEWS_BASE
        reasons: list[str] = []

        if market_acc > 0.70:
            market_w = 0.40
            reasons.append(f"market accuracy {market_acc:.0%} — weight raised")
        if news_acc < 0.50:
            news_w = max(NEWS_BASE * MIN_WEIGHT_FLOOR_RATIO, 0.15)
            reasons.append(f"news accuracy {news_acc:.0%} — weight reduced")

        news_w = max(news_w, NEWS_BASE * MIN_WEIGHT_FLOOR_RATIO)
        market_w = max(market_w, MARKET_BASE * MIN_WEIGHT_FLOOR_RATIO)

        risk_w = max(RISK_MIN_WEIGHT, 1.0 - market_w - news_w)
        if risk_w > RISK_MIN_WEIGHT and market_w + news_w + risk_w > 1.0:
            excess = market_w + news_w + risk_w - 1.0
            market_w = max(
                min_weight_floor(AgentRole.MARKET_ANALYST, market_w),
                market_w - excess / 2,
            )
            news_w = max(
                min_weight_floor(AgentRole.NEWS, news_w),
                news_w - excess / 2,
            )
            risk_w = 1.0 - market_w - news_w

        risk_w = max(RISK_MIN_WEIGHT, risk_w)
        total = market_w + news_w + risk_w
        weights = {
            AgentRole.MARKET_ANALYST: round(market_w / total, 4),
            AgentRole.RISK: round(risk_w / total, 4),
            AgentRole.NEWS: round(news_w / total, 4),
        }

        for v in verdicts:
            v.weight = weights.get(v.agent_id, v.weight)

        if session and reasons:
            await self._log_weights(session, symbol, regime, weights, "; ".join(reasons))

        return weights

    async def vote(
        self,
        symbol: str,
        verdicts: list[AgentVerdict],
        regime: str = "UNKNOWN",
        session: AsyncSession | None = None,
        snapshot: Any | None = None,
    ) -> AgentConsensus:
        await self.compute_weights(session, symbol, regime, verdicts)

        if snapshot is not None:
            from app.services.agent_freshness import apply_dynamic_weight_adjustments

            verdicts, weight_reasons = apply_dynamic_weight_adjustments(
                verdicts, snapshot.indicators, snapshot
            )
        else:
            weight_reasons = []

        vote_scores = compute_vote_scores(verdicts)
        normalized = compute_direction_normalized(verdicts)
        final_direction = direction_from_normalized(normalized)
        final_confidence = compute_weighted_confidence(verdicts, final_direction)

        reasoning_summary = self._build_summary(verdicts, final_direction, final_confidence)
        if weight_reasons:
            reasoning_summary.extend(weight_reasons[:3])

        return AgentConsensus(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            final_direction=final_direction,
            final_confidence=round(final_confidence, 4),
            verdicts=verdicts,
            vote_scores=vote_scores,
            reasoning_summary=reasoning_summary,
        )

    async def _log_weights(
        self,
        session: AsyncSession,
        symbol: str,
        regime: str,
        weights: dict[AgentRole, float],
        reason: str,
    ) -> None:
        log = AgentWeightLog(
            symbol=symbol,
            regime=regime,
            market_weight=weights[AgentRole.MARKET_ANALYST],
            risk_weight=weights[AgentRole.RISK],
            news_weight=weights[AgentRole.NEWS],
            reason=reason,
        )
        session.add(log)
        await session.flush()

    def _build_summary(
        self,
        verdicts: list[AgentVerdict],
        direction: SignalDirection,
        confidence: float,
    ) -> list[str]:
        dir_ar = {"LONG": "شراء", "SHORT": "بيع", "NEUTRAL": "محايد"}
        summary = [
            f"القرار الجماعي: {dir_ar.get(direction.value, direction.value)} "
            f"({confidence:.0%} موزونة)"
        ]
        for v in verdicts:
            summary.append(
                f"{v.agent_name_ar}: {dir_ar.get(v.direction.value, v.direction.value)} "
                f"({v.confidence:.0%}, وزن {v.weight:.0%})"
            )
        return summary
