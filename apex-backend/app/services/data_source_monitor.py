"""Track TwelveData primary source for gold (XAUUSD).

FX pairs use FrankfurterFeed directly. DB fallback is silent (no Telegram).
"""

from __future__ import annotations

from app.logging_config import logger

PRIMARY_SOURCE = "twelvedata"

_failover_active: dict[str, str] = {}


async def report_live_bar_source(symbol: str, source: str) -> None:
    """Log when TwelveData primary recovers after a prior fallback."""
    if source != PRIMARY_SOURCE:
        return

    if symbol in _failover_active:
        fallback = _failover_active.pop(symbol)
        logger.info(
            "data_source_primary_recovered",
            symbol=symbol,
            primary=PRIMARY_SOURCE,
            was_on=fallback,
        )


def clear_failover_state() -> None:
    """Test helper."""
    _failover_active.clear()
