"""Monitor open Telegram trades — news flips, opinion changes, SL proximity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.cache import (
    clear_open_trade_monitor_state,
    get_news_verdict,
    get_open_trade_monitor_state,
    mark_open_trade_warning_sent,
    open_trade_warning_already_sent,
    set_open_trade_monitor_state,
)
from app.logging_config import logger
from app.models.journal import JournalEntry
from app.services.market_data_store import get_latest_price_from_db
from app.services.outcome_tracker import auto_outcome_tracker
from app.services.telegram_notifier import telegram_notifier

WarningType = Literal["contrary_news", "news_opinion_changed", "near_sl"]


def normalize_direction(value: str | None) -> str:
    if not value:
        return "NEUTRAL"
    return str(value).strip().upper()


def is_contrary_news(trade_direction: str, news_direction: str) -> bool:
    trade = normalize_direction(trade_direction)
    news = normalize_direction(news_direction)
    if news == "NEUTRAL":
        return False
    return (trade == "LONG" and news == "SHORT") or (trade == "SHORT" and news == "LONG")


def is_news_opinion_changed(baseline_direction: str | None, current_direction: str) -> bool:
    baseline = normalize_direction(baseline_direction)
    current = normalize_direction(current_direction)
    if baseline == "NEUTRAL":
        return False
    return baseline != current


def is_near_stop_loss(
    *,
    direction: str,
    entry_price: float,
    stop_loss: float,
    current_price: float,
    near_ratio: float | None = None,
) -> bool:
    ratio = near_ratio if near_ratio is not None else settings.open_trade_sl_near_ratio
    if ratio <= 0:
        return False

    trade = normalize_direction(direction)
    if trade == "LONG":
        risk = entry_price - stop_loss
        if risk <= 0:
            return False
        remaining = current_price - stop_loss
        return remaining / risk <= ratio

    if trade == "SHORT":
        risk = stop_loss - entry_price
        if risk <= 0:
            return False
        remaining = stop_loss - current_price
        return remaining / risk <= ratio

    return False


def warning_detail_ar(warning_type: WarningType) -> str:
    if warning_type == "near_sl":
        return "السعر اقترب من وقف الخسارة — فكر في إغلاق الصفقة يدوياً"
    return "الاتجاه تغير — فكر في إغلاق الصفقة يدوياً"


async def register_open_trade_monitor(
    *,
    journal_id: int,
    symbol: str,
    trade_direction: str,
) -> None:
    """Capture news baseline when a Telegram signal opens a monitored trade."""
    news_raw = await get_news_verdict(symbol)
    news_direction = normalize_direction(news_raw.get("direction") if news_raw else None)
    await set_open_trade_monitor_state(
        journal_id,
        {
            "journal_id": journal_id,
            "symbol": symbol,
            "trade_direction": normalize_direction(trade_direction),
            "news_direction_at_open": news_direction,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        },
    )


async def _load_pending_open_trades(session: AsyncSession) -> list[JournalEntry]:
    result = await session.execute(
        select(JournalEntry)
        .where(
            JournalEntry.source == "system_signal",
            JournalEntry.auto_outcome.is_(None),
        )
        .order_by(JournalEntry.created_at.asc())
    )
    return list(result.scalars().all())


async def _evaluate_warnings_for_entry(
    session: AsyncSession,
    entry: JournalEntry,
) -> int:
    state = await get_open_trade_monitor_state(entry.id)
    if state is None:
        await register_open_trade_monitor(
            journal_id=entry.id,
            symbol=entry.symbol,
            trade_direction=entry.direction,
        )
        state = await get_open_trade_monitor_state(entry.id)

    news_raw = await get_news_verdict(entry.symbol)
    news_direction = normalize_direction(news_raw.get("direction") if news_raw else None)
    baseline_direction = (
        state.get("news_direction_at_open") if state else None
    )

    warnings: list[WarningType] = []
    if is_contrary_news(entry.direction, news_direction):
        warnings.append("contrary_news")
    elif is_news_opinion_changed(baseline_direction, news_direction):
        warnings.append("news_opinion_changed")

    latest = await get_latest_price_from_db(entry.symbol)
    if latest and latest.get("price") is not None:
        current_price = float(latest["price"])
        if is_near_stop_loss(
            direction=entry.direction,
            entry_price=entry.entry_price,
            stop_loss=entry.stop_loss,
            current_price=current_price,
        ):
            warnings.append("near_sl")

    sent = 0
    for warning_type in warnings:
        if await open_trade_warning_already_sent(entry.id, warning_type):
            continue
        detail = warning_detail_ar(warning_type)
        ok = await telegram_notifier.send_open_trade_warning(
            entry.symbol,
            entry.direction,
            detail,
        )
        if ok:
            await mark_open_trade_warning_sent(entry.id, warning_type)
            sent += 1
            logger.info(
                "open_trade_warning_sent",
                journal_id=entry.id,
                symbol=entry.symbol,
                warning_type=warning_type,
            )
    return sent


async def run_open_trade_monitor_cycle(session: AsyncSession | None = None) -> dict[str, int]:
    """
    Resolve TP/SL/expiry first, then warn on still-open Telegram trades.
    Returns counters for logging/metrics.
    """
    from app.database import AsyncSessionLocal

    resolved = 0
    warnings_sent = 0

    if session is None:
        async with AsyncSessionLocal() as owned_session:
            resolved = await auto_outcome_tracker.track_pending_outcomes(owned_session)
            pending = await _load_pending_open_trades(owned_session)
            for entry in pending:
                warnings_sent += await _evaluate_warnings_for_entry(owned_session, entry)
    else:
        resolved = await auto_outcome_tracker.track_pending_outcomes(session)
        pending = await _load_pending_open_trades(session)
        for entry in pending:
            warnings_sent += await _evaluate_warnings_for_entry(session, entry)

    return {"resolved": resolved, "warnings_sent": warnings_sent}


async def clear_open_trade_monitor(journal_id: int) -> None:
    await clear_open_trade_monitor_state(journal_id)
