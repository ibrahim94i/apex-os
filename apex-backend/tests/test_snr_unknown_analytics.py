"""SNR analytics unknown bucket separate from outside_zone."""

from datetime import datetime, timezone

from app.models.journal import JournalEntry
from app.services.trading_journal_service import build_snr_analytics


def test_unknown_snr_not_counted_in_outside_zone() -> None:
    now = datetime.now(timezone.utc)
    entries = [
        JournalEntry(
            symbol="XAUUSD",
            direction="LONG",
            entry_price=100,
            exit_price=100,
            stop_loss=95,
            take_profit=110,
            source="system_signal",
            emotion="hesitant",
            result="pending",
            follow_up_status="pending",
            snr_state=None,
            auto_outcome="win",
            pnl=0,
            pnl_pct=0,
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
            result="pending",
            follow_up_status="pending",
            snr_state="normal",
            auto_outcome="loss",
            pnl=0,
            pnl_pct=0,
            closed_at=now,
        ),
        JournalEntry(
            symbol="BTCUSDT",
            direction="LONG",
            entry_price=100,
            exit_price=95,
            stop_loss=95,
            take_profit=110,
            source="system_signal",
            emotion="hesitant",
            result="pending",
            follow_up_status="pending",
            snr_state="inside_zone",
            auto_outcome="win",
            pnl=0,
            pnl_pct=0,
            closed_at=now,
        ),
    ]
    analytics = build_snr_analytics(entries)
    assert analytics.unknown_snr_resolved == 1
    assert analytics.unknown_snr_win_rate == 1.0
    assert analytics.outside_zone_resolved == 1
    assert analytics.outside_zone_win_rate == 0.0
    assert analytics.inside_zone_resolved == 1
    assert analytics.inside_zone_win_rate == 1.0
