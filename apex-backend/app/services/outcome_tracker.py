"""Auto Outcome Tracker — monitor TP/SL/expiry after Telegram signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import logger
from app.models import PriceBar, TradingSignal
from app.models.journal import JournalEntry
from app.models.phase3 import SignalOutcome

EXPIRY_HOURS = 48.0
AutoOutcome = Literal["win", "loss", "expired"]


@dataclass(frozen=True)
class OutcomeTrackResult:
    outcome: AutoOutcome
    time_to_outcome_hours: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    exit_price: float | None = None


@dataclass(frozen=True)
class PriceSample:
    timestamp: datetime
    high: float
    low: float
    close: float


def _hours_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 3600.0)


def evaluate_auto_outcome(
    *,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    opened_at: datetime,
    samples: list[PriceSample],
    now: datetime | None = None,
    expiry_hours: float = EXPIRY_HOURS,
) -> OutcomeTrackResult | None:
    """
    Return outcome when TP/SL hit or expiry reached; None while still pending.
    SL is checked before TP on the same bar (conservative).
    """
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    mfe = 0.0
    mae = 0.0
    is_long = direction == "LONG"

    for sample in samples:
        if sample.timestamp < opened_at:
            continue

        if is_long:
            mfe = max(mfe, sample.high - entry_price)
            mae = max(mae, entry_price - sample.low)
            if sample.low <= stop_loss:
                return OutcomeTrackResult(
                    outcome="loss",
                    time_to_outcome_hours=round(_hours_between(opened_at, sample.timestamp), 4),
                    max_favorable_excursion=round(mfe, 6),
                    max_adverse_excursion=round(mae, 6),
                    exit_price=stop_loss,
                )
            if sample.high >= take_profit:
                return OutcomeTrackResult(
                    outcome="win",
                    time_to_outcome_hours=round(_hours_between(opened_at, sample.timestamp), 4),
                    max_favorable_excursion=round(mfe, 6),
                    max_adverse_excursion=round(mae, 6),
                    exit_price=take_profit,
                )
        else:
            mfe = max(mfe, entry_price - sample.low)
            mae = max(mae, sample.high - entry_price)
            if sample.high >= stop_loss:
                return OutcomeTrackResult(
                    outcome="loss",
                    time_to_outcome_hours=round(_hours_between(opened_at, sample.timestamp), 4),
                    max_favorable_excursion=round(mfe, 6),
                    max_adverse_excursion=round(mae, 6),
                    exit_price=stop_loss,
                )
            if sample.low <= take_profit:
                return OutcomeTrackResult(
                    outcome="win",
                    time_to_outcome_hours=round(_hours_between(opened_at, sample.timestamp), 4),
                    max_favorable_excursion=round(mfe, 6),
                    max_adverse_excursion=round(mae, 6),
                    exit_price=take_profit,
                )

    elapsed = _hours_between(opened_at, current)
    if elapsed >= expiry_hours:
        return OutcomeTrackResult(
            outcome="expired",
            time_to_outcome_hours=round(expiry_hours, 4),
            max_favorable_excursion=round(mfe, 6),
            max_adverse_excursion=round(mae, 6),
            exit_price=None,
        )
    return None


def trading_signal_outcome_value(outcome: AutoOutcome) -> str:
    return {
        "win": SignalOutcome.WIN.value,
        "loss": SignalOutcome.LOSS.value,
        "expired": SignalOutcome.EXPIRED.value,
    }[outcome]


class AutoOutcomeTracker:
    async def track_pending_outcomes(
        self,
        session: AsyncSession,
        symbol: str | None = None,
    ) -> int:
        """Evaluate pending journal/system signals; returns count newly resolved."""
        query = select(JournalEntry).where(
            JournalEntry.source == "system_signal",
            JournalEntry.auto_outcome.is_(None),
        )
        if symbol:
            query = query.where(JournalEntry.symbol == symbol)
        result = await session.execute(query.order_by(JournalEntry.created_at.asc()))
        pending = list(result.scalars().all())

        resolved = 0
        win_loss_resolved = False
        for entry in pending:
            track_result = await self._evaluate_journal_entry(session, entry)
            if track_result is None:
                continue
            await self._apply_journal_outcome(entry, track_result)
            if entry.trading_signal_id:
                ts = await session.get(TradingSignal, entry.trading_signal_id)
                if ts is not None and ts.outcome is None:
                    self._apply_trading_signal_outcome(ts, track_result)
            resolved += 1
            if track_result.outcome in ("win", "loss"):
                win_loss_resolved = True
            logger.info(
                "auto_outcome_resolved",
                symbol=entry.symbol,
                journal_id=entry.id,
                outcome=track_result.outcome,
                time_to_outcome=track_result.time_to_outcome_hours,
                mfe=track_result.max_favorable_excursion,
                mae=track_result.max_adverse_excursion,
            )

        if resolved:
            await session.commit()
            if win_loss_resolved:
                from app.services.memory_engine import memory_engine

                symbols = {
                    entry.symbol
                    for entry in pending
                    if entry.auto_outcome in ("win", "loss")
                }
                for sym in symbols:
                    await memory_engine.record_signal_outcome(session, sym)
        return resolved

    async def _evaluate_journal_entry(
        self,
        session: AsyncSession,
        entry: JournalEntry,
    ) -> OutcomeTrackResult | None:
        opened_at = entry.closed_at or entry.created_at
        if opened_at is None:
            return None

        bars_result = await session.execute(
            select(PriceBar)
            .where(
                and_(
                    PriceBar.symbol == entry.symbol,
                    PriceBar.timestamp >= opened_at,
                )
            )
            .order_by(PriceBar.timestamp.asc())
        )
        bars = bars_result.scalars().all()
        samples = [
            PriceSample(
                timestamp=bar.timestamp,
                high=bar.high,
                low=bar.low,
                close=bar.close,
            )
            for bar in bars
        ]

        from app.services.market_data_store import get_latest_price_from_db

        latest = await get_latest_price_from_db(entry.symbol)
        now = datetime.now(timezone.utc)
        if latest:
            ts_raw = latest.get("timestamp")
            if isinstance(ts_raw, str):
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            elif isinstance(ts_raw, datetime):
                ts = ts_raw
            else:
                ts = now
            price = float(latest["close"])
            if not samples or samples[-1].timestamp < ts:
                samples.append(
                    PriceSample(timestamp=ts, high=price, low=price, close=price)
                )

        return evaluate_auto_outcome(
            direction=entry.direction,
            entry_price=entry.entry_price,
            stop_loss=entry.stop_loss,
            take_profit=entry.take_profit,
            opened_at=opened_at,
            samples=samples,
            now=now,
        )

    async def _apply_journal_outcome(
        self,
        entry: JournalEntry,
        result: OutcomeTrackResult,
    ) -> None:
        entry.auto_outcome = result.outcome
        entry.time_to_outcome = result.time_to_outcome_hours
        entry.max_favorable_excursion = result.max_favorable_excursion
        entry.max_adverse_excursion = result.max_adverse_excursion

    def _apply_trading_signal_outcome(
        self,
        signal: TradingSignal,
        result: OutcomeTrackResult,
    ) -> None:
        signal.outcome = trading_signal_outcome_value(result.outcome)
        signal.time_in_trade_hours = result.time_to_outcome_hours
        signal.max_favorable_excursion = result.max_favorable_excursion
        signal.max_adverse_excursion = result.max_adverse_excursion
        if result.exit_price is not None:
            signal.actual_exit_price = result.exit_price
            risk = abs(signal.entry_price - signal.stop_loss)
            if risk > 0 and result.outcome == "win":
                signal.rr_achieved = round(
                    abs(result.exit_price - signal.entry_price) / risk,
                    4,
                )
            elif result.outcome == "loss":
                signal.rr_achieved = -1.0


auto_outcome_tracker = AutoOutcomeTracker()
