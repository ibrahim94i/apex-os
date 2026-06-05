"""Adaptive weighted voting engine with risk agent veto."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase3 import AgentWeightLog
from app.schemas import SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict
from app.services.memory_engine import memory_engine

RISK_MIN_WEIGHT = 0.40
MARKET_BASE = 0.35
NEWS_BASE = 0.25


class AdaptiveWeightedEngine:
    DIRECTION_VALUES = {
        SignalDirection.LONG: 1.0,
        SignalDirection.SHORT: -1.0,
        SignalDirection.NEUTRAL: 0.0,
    }

    async def compute_weights(
        self,
        session: AsyncSession | None,
        symbol: str,
        regime: str,
        verdicts: list[AgentVerdict],
    ) -> dict[AgentRole, float]:
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
            reasons.append(f"محلل السوق دقة {market_acc:.0%} — رفع الوزن")
        if news_acc < 0.50:
            news_w = 0.15
            reasons.append(f"وكيل الأخبار دقة {news_acc:.0%} — خفض الوزن")

        risk_w = max(RISK_MIN_WEIGHT, 1.0 - market_w - news_w)
        if risk_w > RISK_MIN_WEIGHT and market_w + news_w + risk_w > 1.0:
            excess = market_w + news_w + risk_w - 1.0
            market_w = max(0.15, market_w - excess / 2)
            news_w = max(0.10, news_w - excess / 2)
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

        vote_scores: dict[str, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for verdict in verdicts:
            direction_val = self.DIRECTION_VALUES[verdict.direction]
            score = direction_val * verdict.confidence * verdict.weight
            vote_scores[verdict.agent_id.value] = round(score, 4)
            weighted_sum += score
            total_weight += verdict.weight

        normalized = weighted_sum / total_weight if total_weight else 0.0
        final_confidence = min(abs(normalized), 1.0)

        if normalized > 0.15:
            final_direction = SignalDirection.LONG
        elif normalized < -0.15:
            final_direction = SignalDirection.SHORT
        else:
            final_direction = SignalDirection.NEUTRAL

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
