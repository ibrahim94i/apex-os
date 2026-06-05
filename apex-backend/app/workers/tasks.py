"""Celery background tasks."""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.config import settings
from app.core.cache import get_feed_last_update, set_kill_switch_status
from app.database import AsyncSessionLocal
from app.engines.kill_switch import kill_switch
from app.logging_config import logger
from app.models import PriceBar
from app.workers.celery_app import celery_app


def _run_async(coro):  # type: ignore[no-untyped-def]
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.tasks.evaluate_kill_switch")
def evaluate_kill_switch() -> dict:
    async def _evaluate() -> dict:
        async with AsyncSessionLocal() as session:
            await kill_switch.load_from_cache()
            status = await kill_switch.evaluate(session)
            await session.commit()
            return status.model_dump(mode="json")

    result = _run_async(_evaluate())
    logger.info("kill_switch_evaluated", status=result.get("status"))
    return result


@celery_app.task(name="app.workers.tasks.check_feed_staleness")
def check_feed_staleness() -> dict:
    async def _check() -> dict:
        from app.config.assets import ACTIVE_SYMBOLS

        stale_symbols: list[str] = []
        now = datetime.now(timezone.utc)

        for symbol in ACTIVE_SYMBOLS:
            from app.services.feed_freshness import feed_poll_age_seconds, is_feed_poll_stale
            from app.services.market_hours import is_market_open

            if not is_market_open(symbol):
                continue
            if not await is_feed_poll_stale(symbol):
                continue
            last_update = await get_feed_last_update(symbol)
            stale_symbols.append(symbol)

        if stale_symbols:
            await set_kill_switch_status({
                "status": "ACTIVE",
                "reason": f"Stale feeds: {', '.join(stale_symbols)}",
                "triggered_at": now.isoformat(),
            })
            logger.warning("feeds_stale", symbols=stale_symbols)

        return {"stale_symbols": stale_symbols, "checked_at": now.isoformat()}

    return _run_async(_check())


@celery_app.task(name="app.workers.tasks.cleanup_old_bars")
def cleanup_old_bars(days: int = 30) -> dict:
    async def _cleanup() -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(PriceBar).where(PriceBar.timestamp < cutoff)
            )
            await session.commit()
            return {"deleted": result.rowcount, "cutoff": cutoff.isoformat()}

    return _run_async(_cleanup())
