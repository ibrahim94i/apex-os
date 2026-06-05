"""High Selectivity Mode — phased confidence thresholds."""

from datetime import date, datetime, timezone

from app.config import settings


def effective_min_confidence_pct(at: datetime | None = None) -> float:
    """70% during learning period, 80% after learning_period_days."""
    start_raw = settings.high_selectivity_learning_start.strip()
    if not start_raw:
        return settings.min_signal_confidence_pct

    try:
        start = date.fromisoformat(start_raw)
    except ValueError:
        return settings.min_signal_confidence_pct

    now = (at or datetime.now(timezone.utc)).date()
    days = (now - start).days
    if days >= settings.learning_period_days:
        return settings.min_signal_confidence_pct_post_learning
    return settings.min_signal_confidence_pct


def effective_min_confidence(at: datetime | None = None) -> float:
    return effective_min_confidence_pct(at) / 100.0


def selectivity_confidence_floor() -> float:
    """Hard minimum for agent-driven signals (below = no signal)."""
    return settings.selectivity_confidence_floor_pct / 100.0


def strong_agent_bypass_threshold() -> float:
    """Market analyst + risk agent must exceed this to skip RSI/ATR filters."""
    return settings.strong_agent_bypass_threshold_pct / 100.0
