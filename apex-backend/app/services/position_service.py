"""Open position queries for conflict detection."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TradingSignal


async def get_open_positions(session: AsyncSession, symbol: str) -> list[TradingSignal]:
    """Return unresolved LONG/SHORT signals (open positions)."""
    result = await session.execute(
        select(TradingSignal).where(
            TradingSignal.symbol == symbol,
            TradingSignal.outcome.is_(None),
            TradingSignal.direction.in_(["LONG", "SHORT"]),
        ).order_by(TradingSignal.timestamp.desc())
    )
    return list(result.scalars().all())


def detect_position_signal_conflict(
    open_positions: list[TradingSignal],
    new_direction: str,
    confidence: float,
    *,
    threshold: float = 0.75,
) -> tuple[bool, str | None]:
    """
    Detect emergency conflict: open position vs strong opposing signal.
    Returns (should_alert, alert_type).
    """
    if confidence <= threshold:
        return False, None

    for pos in open_positions:
        if pos.direction == "SHORT" and new_direction == "LONG":
            return True, "market_turned_bullish"
        if pos.direction == "LONG" and new_direction == "SHORT":
            return True, "market_turned_bearish"

    return False, None
