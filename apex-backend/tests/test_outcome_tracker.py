"""Tests for Auto Outcome Tracker."""

from datetime import datetime, timedelta, timezone

from app.services.outcome_tracker import (
    EXPIRY_HOURS,
    OutcomeTrackResult,
    PriceSample,
    evaluate_auto_outcome,
)


def _ts(hours: float) -> datetime:
    base = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    return base + timedelta(hours=hours)


def test_long_tp_is_win() -> None:
    result = evaluate_auto_outcome(
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        opened_at=_ts(0),
        samples=[PriceSample(_ts(1), high=111.0, low=99.0, close=108.0)],
        now=_ts(2),
    )
    assert result == OutcomeTrackResult(
        outcome="win",
        time_to_outcome_hours=1.0,
        max_favorable_excursion=11.0,
        max_adverse_excursion=1.0,
        exit_price=110.0,
    )


def test_long_sl_is_loss() -> None:
    result = evaluate_auto_outcome(
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        opened_at=_ts(0),
        samples=[PriceSample(_ts(2), high=101.0, low=94.0, close=96.0)],
        now=_ts(3),
    )
    assert result is not None
    assert result.outcome == "loss"
    assert result.exit_price == 95.0


def test_short_tp_is_win() -> None:
    result = evaluate_auto_outcome(
        direction="SHORT",
        entry_price=100.0,
        stop_loss=105.0,
        take_profit=90.0,
        opened_at=_ts(0),
        samples=[PriceSample(_ts(1), high=101.0, low=89.0, close=92.0)],
        now=_ts(2),
    )
    assert result is not None
    assert result.outcome == "win"
    assert result.exit_price == 90.0


def test_expires_after_2_hours() -> None:
    result = evaluate_auto_outcome(
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        opened_at=_ts(0),
        samples=[PriceSample(_ts(1), high=102.0, low=98.0, close=101.0)],
        now=_ts(EXPIRY_HOURS),
    )
    assert result is not None
    assert result.outcome == "expired"
    assert result.time_to_outcome_hours == EXPIRY_HOURS


def test_still_pending_before_expiry() -> None:
    result = evaluate_auto_outcome(
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        opened_at=_ts(0),
        samples=[PriceSample(_ts(0.5), high=102.0, low=98.0, close=101.0)],
        now=_ts(1),
    )
    assert result is None
