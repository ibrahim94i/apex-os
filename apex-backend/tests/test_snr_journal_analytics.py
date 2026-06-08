"""SNR fields on signals and journal analytics."""

from datetime import datetime, timezone

from app.engines.final_decision_engine import snr_penalty_points, snr_state_record_value
from app.models.journal import JournalEntry
from app.services.trading_journal_service import build_snr_analytics


def test_snr_state_record_value() -> None:
    assert snr_state_record_value("INSIDE_ZONE") == "inside_zone"
    assert snr_state_record_value("BREAKOUT_CONFIRMED") == "breakout_confirmed"


def test_snr_penalty_points() -> None:
    assert snr_penalty_points("INSIDE_ZONE") == -20
    assert snr_penalty_points("ZONE_EDGE") == -10
    assert snr_penalty_points("NORMAL") == 0
    assert snr_penalty_points("BREAKOUT_CONFIRMED") == 0


def test_snr_analytics_inside_vs_outside() -> None:
    now = datetime.now(timezone.utc)
    entries = [
        JournalEntry(
            symbol="XAUUSD",
            direction="LONG",
            entry_price=100,
            exit_price=110,
            stop_loss=95,
            take_profit=115,
            source="system_signal",
            emotion="hesitant",
            result="win",
            follow_up_status="entered",
            snr_state="inside_zone",
            snr_penalty=-20,
            pnl=10,
            pnl_pct=10,
            closed_at=now,
        ),
        JournalEntry(
            symbol="XAUUSD",
            direction="LONG",
            entry_price=100,
            exit_price=95,
            stop_loss=95,
            take_profit=115,
            source="system_signal",
            emotion="hesitant",
            result="loss",
            follow_up_status="lost",
            snr_state="inside_zone",
            snr_penalty=-20,
            pnl=-5,
            pnl_pct=-5,
            closed_at=now,
        ),
        JournalEntry(
            symbol="EURUSD",
            direction="SHORT",
            entry_price=1.1,
            exit_price=1.08,
            stop_loss=1.12,
            take_profit=1.05,
            source="system_signal",
            emotion="hesitant",
            result="win",
            follow_up_status="entered",
            snr_state="normal",
            snr_penalty=0,
            pnl=0.02,
            pnl_pct=1.8,
            closed_at=now,
        ),
        JournalEntry(
            symbol="GBPUSD",
            direction="LONG",
            entry_price=1.25,
            exit_price=1.25,
            stop_loss=1.24,
            take_profit=1.27,
            source="system_signal",
            emotion="hesitant",
            result="pending",
            follow_up_status="pending",
            snr_state="zone_edge",
            snr_penalty=-10,
            pnl=0,
            pnl_pct=0,
            closed_at=now,
        ),
    ]
    analytics = build_snr_analytics(entries)
    assert analytics.inside_zone_resolved == 2
    assert analytics.inside_zone_win_rate == 0.5
    assert analytics.outside_zone_resolved == 1
    assert analytics.outside_zone_win_rate == 1.0
    assert analytics.unknown_snr_resolved == 0
