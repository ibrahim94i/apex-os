"""Agent data freshness validation and dynamic weight adjustments."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base_weights import all_agents_high_confidence, min_weight_floor
from app.config import settings
from app.schemas import IndicatorSnapshotSchema, SignalDirection
from app.schemas.agent import AgentRole, AgentVerdict, MarketSnapshot

STALE_WEIGHT_MULTIPLIER = 0.25
INCONSISTENT_WEIGHT_MULTIPLIER = 0.50


def _data_age_seconds(snapshot: MarketSnapshot) -> float:
    now = datetime.now(timezone.utc)
    ts = snapshot.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (now - ts).total_seconds())


def annotate_verdict_freshness(
    verdicts: list[AgentVerdict],
    snapshot: MarketSnapshot,
) -> list[AgentVerdict]:
    """Mark each verdict stale when snapshot feed or age exceeds limit."""
    max_age = settings.agent_data_max_age_seconds
    age = _data_age_seconds(snapshot)
    snapshot_stale = snapshot.feed_stale or age > max_age
    now = datetime.now(timezone.utc)

    updated: list[AgentVerdict] = []
    for v in verdicts:
        is_stale = snapshot_stale or v.is_stale
        data_age = v.data_age_seconds if v.data_age_seconds is not None else age
        updated.append(
            v.model_copy(
                update={
                    "analyzed_at": v.analyzed_at or now,
                    "is_stale": is_stale,
                    "data_age_seconds": round(data_age, 2),
                }
            )
        )
    return updated


def validate_agent_data_freshness(
    snapshot: MarketSnapshot,
    verdicts: list[AgentVerdict],
) -> tuple[bool, str | None]:
    """Reject consensus when any agent input is stale."""
    max_age = settings.agent_data_max_age_seconds
    if snapshot.feed_stale:
        return False, "feed_stale"

    age = _data_age_seconds(snapshot)
    if age > max_age:
        return False, "snapshot_data_too_old"

    for v in verdicts:
        if v.is_stale:
            return False, f"agent_stale:{v.agent_id.value}"
        if v.data_age_seconds is not None and v.data_age_seconds > max_age:
            return False, f"agent_data_too_old:{v.agent_id.value}"

    return True, None


def is_verdict_indicator_inconsistent(
    verdict: AgentVerdict,
    indicators: IndicatorSnapshotSchema,
) -> bool:
    """True when agent direction conflicts with core indicator bias."""
    if verdict.direction == SignalDirection.NEUTRAL:
        return False

    bearish_rsi = indicators.rsi is not None and indicators.rsi > 70
    bullish_rsi = indicators.rsi is not None and indicators.rsi < 30
    macd_bearish = (
        indicators.macd is not None
        and indicators.macd_signal is not None
        and indicators.macd < indicators.macd_signal
    )
    macd_bullish = (
        indicators.macd is not None
        and indicators.macd_signal is not None
        and indicators.macd > indicators.macd_signal
    )
    below_ema200 = (
        indicators.ema_200 is not None
        and indicators.ema_50 is not None
        and indicators.ema_50 < indicators.ema_200
    )
    above_ema200 = (
        indicators.ema_200 is not None
        and indicators.ema_50 is not None
        and indicators.ema_50 > indicators.ema_200
    )

    if verdict.direction == SignalDirection.LONG:
        conflicts = sum(
            [
                bearish_rsi,
                macd_bearish,
                below_ema200,
            ]
        )
        return conflicts >= 2

    if verdict.direction == SignalDirection.SHORT:
        conflicts = sum(
            [
                bullish_rsi,
                macd_bullish,
                above_ema200,
            ]
        )
        return conflicts >= 2

    return False


def apply_dynamic_weight_adjustments(
    verdicts: list[AgentVerdict],
    indicators: IndicatorSnapshotSchema,
    snapshot: MarketSnapshot,
) -> tuple[list[AgentVerdict], list[str]]:
    """Reduce weights for stale or indicator-inconsistent agents."""
    if all_agents_high_confidence(verdicts):
        return verdicts, []

    max_age = settings.agent_data_max_age_seconds
    reasons: list[str] = []
    adjusted: list[AgentVerdict] = []

    for v in verdicts:
        weight = v.weight
        floor = min_weight_floor(v.agent_id, v.weight)
        age = v.data_age_seconds or _data_age_seconds(snapshot)

        if v.is_stale or age > max_age:
            weight *= STALE_WEIGHT_MULTIPLIER
            reasons.append(f"{v.agent_name_ar}: stale data — weight reduced")
        elif is_verdict_indicator_inconsistent(v, indicators):
            weight *= INCONSISTENT_WEIGHT_MULTIPLIER
            reasons.append(f"{v.agent_name_ar}: indicator conflict — weight reduced")

        adjusted.append(v.model_copy(update={"weight": round(max(weight, floor), 4)}))

    return adjusted, reasons
