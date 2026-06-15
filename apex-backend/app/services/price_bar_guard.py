"""Guardrails — block external H1 writes when MetaTrader price feed is live."""

from __future__ import annotations

from app.logging_config import logger


async def should_block_external_price_bars(symbol: str) -> bool:
    """Return True when Binance/TwelveData must not write to price_bars."""
    from app.core.cache import get_metatrader_price
    from app.services.live_price_resolver import is_metatrader_connected

    mt_raw = await get_metatrader_price(symbol)
    if is_metatrader_connected(symbol, mt_raw):
        return True
    return False


async def log_blocked_external_bar(symbol: str, source: str, *, context: str) -> None:
    logger.info(
        "price_bar_external_write_blocked",
        symbol=symbol,
        source=source,
        context=context,
    )
