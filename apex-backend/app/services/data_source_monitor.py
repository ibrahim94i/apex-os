"""Track market data source health and alert on primary-source failover."""

from __future__ import annotations

from app.logging_config import logger

PRIMARY_SOURCE = "twelvedata"

_failover_active: dict[str, str] = {}


async def report_live_bar_source(symbol: str, source: str) -> None:
    """Notify when primary source recovers or failover occurs."""
    from app.services.telegram_notifier import telegram_notifier

    if source == PRIMARY_SOURCE:
        if symbol in _failover_active:
            fallback = _failover_active.pop(symbol)
            logger.info(
                "data_source_primary_recovered",
                symbol=symbol,
                primary=PRIMARY_SOURCE,
                was_on=fallback,
            )
            if telegram_notifier.enabled:
                await telegram_notifier.send_data_source_recovery_alert(
                    symbol,
                    primary=PRIMARY_SOURCE,
                    fallback=fallback,
                )
        return

    previous = _failover_active.get(symbol)
    if previous == source:
        return

    _failover_active[symbol] = source
    logger.warning(
        "data_source_failover",
        symbol=symbol,
        primary=PRIMARY_SOURCE,
        fallback=source,
    )
    if telegram_notifier.enabled:
        await telegram_notifier.send_data_source_failover_alert(
            symbol,
            primary=PRIMARY_SOURCE,
            fallback=source,
        )


def clear_failover_state() -> None:
    """Test helper."""
    _failover_active.clear()
