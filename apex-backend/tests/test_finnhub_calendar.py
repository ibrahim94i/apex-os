"""Finnhub economic calendar and blackout gate."""

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.agent import EconomicEventSchema
from app.services.economic_calendar_gate import check_economic_calendar_gate
from app.services.finnhub_calendar import (
    fetch_upcoming_high_impact_events,
    find_event_in_blackout_window,
    find_imminent_event,
    minutes_until_event,
    parse_event_time,
)


def _event(minutes_from_now: float, name: str = "CPI") -> EconomicEventSchema:
    ref = datetime.now(timezone.utc)
    return EconomicEventSchema(
        event=name,
        country="US",
        impact="high",
        event_time=ref + timedelta(minutes=minutes_from_now),
    )


def test_parse_event_time_utc() -> None:
    dt = parse_event_time("2026-06-05 14:30:00")
    assert dt is not None
    assert dt.tzinfo == timezone.utc


def test_blackout_pre_event_20_minutes() -> None:
    ref = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    ev = EconomicEventSchema(
        event="NFP",
        country="US",
        impact="high",
        event_time=ref + timedelta(minutes=20),
    )
    assert find_event_in_blackout_window([ev], ref) is not None


def test_blackout_post_event_10_minutes() -> None:
    ref = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    ev = EconomicEventSchema(
        event="NFP",
        country="US",
        impact="high",
        event_time=ref - timedelta(minutes=10),
    )
    assert find_event_in_blackout_window([ev], ref) is not None


def test_blackout_clear_20_minutes_after() -> None:
    ref = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    ev = EconomicEventSchema(
        event="NFP",
        country="US",
        impact="high",
        event_time=ref - timedelta(minutes=20),
    )
    assert find_event_in_blackout_window([ev], ref) is None


def test_gate_blocks_pre_event() -> None:
    ref = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    ev = EconomicEventSchema(
        event="FOMC",
        country="US",
        impact="high",
        event_time=ref + timedelta(minutes=15),
    )
    ok, reason = check_economic_calendar_gate([ev], ref)
    assert ok is False
    assert reason == "economic_calendar_pre_event"


def test_gate_blocks_post_event() -> None:
    ref = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    ev = EconomicEventSchema(
        event="FOMC",
        country="US",
        impact="high",
        event_time=ref - timedelta(minutes=5),
    )
    ok, reason = check_economic_calendar_gate([ev], ref)
    assert ok is False
    assert reason == "economic_calendar_post_event"


def test_imminent_within_60_minutes() -> None:
    ref = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    ev = EconomicEventSchema(
        event="GDP",
        country="EU",
        impact="high",
        event_time=ref + timedelta(minutes=45),
    )
    found = find_imminent_event([ev], ref, within_minutes=60)
    assert found is not None
    assert found.event == "GDP"


@pytest.mark.asyncio
async def test_fetch_filters_high_impact_only() -> None:
    ref = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "event": "Low Event",
            "country": "US",
            "impact": "low",
            "time": "2026-06-05 13:00:00",
        },
        {
            "event": "CPI",
            "country": "US",
            "impact": "high",
            "time": "2026-06-05 14:00:00",
            "estimate": 3.2,
        },
    ]
    with pytest.MonkeyPatch.context() as mp:
        from app.services import finnhub_calendar as cal_mod

        mp.setattr(cal_mod, "_CACHE", None)

        async def fake_rows(from_date: str, to_date: str) -> list:
            return rows

        mp.setattr(cal_mod, "_fetch_calendar_rows", fake_rows)
        mp.setattr(cal_mod, "_is_configured", lambda: True)

        events = await fetch_upcoming_high_impact_events(
            hours_ahead=24,
            reference_time=ref,
        )
    assert len(events) == 1
    assert events[0].event == "CPI"
    assert events[0].impact == "high"


def test_news_prompt_includes_calendar() -> None:
    from app.agents.news.prompt import build_user_prompt
    from app.schemas import KillSwitchStatusSchema, RegimeSnapshotSchema, RegimeType
    from app.schemas.snapshots import IndicatorSnapshotSchema
    from app.schemas.agent import MarketSnapshot

    now = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    snap = MarketSnapshot(
        symbol="EURUSD",
        timestamp=now,
        price=1.08,
        indicators=IndicatorSnapshotSchema(symbol="EURUSD", timestamp=now, rsi=50.0),
        regime=RegimeSnapshotSchema(
            symbol="EURUSD",
            timestamp=now,
            regime=RegimeType.RANGING,
            confidence=0.5,
        ),
        kill_switch=KillSwitchStatusSchema(status="INACTIVE"),
        account_balance=10000.0,
        max_risk_pct=1.0,
        max_drawdown_pct=5.0,
        upcoming_events=[
            EconomicEventSchema(
                event="ECB Rate",
                country="EU",
                impact="high",
                event_time=now + timedelta(minutes=30),
            )
        ],
    )
    prompt = build_user_prompt(snap)
    assert "التقويم الاقتصادي" in prompt
    assert "ECB Rate" in prompt
    assert "تحذير" in prompt
