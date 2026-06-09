"""Background loops — hourly reports, market status, and feed health."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.config import settings
from app.logging_config import logger
from app.services.feed_health_service import run_recovery_cycle
from app.services.hourly_report_service import publish_hourly_report
from app.services.market_hours import is_market_open, symbols_with_scheduled_reopen
from app.services.market_status_service import build_all_market_statuses
from app.websocket.manager import broadcaster

_market_was_open: dict[str, bool] = {}


async def _agent_consensus_watch_loop() -> None:
    """Fill missing agent consensus sequentially for active symbols."""
    from app.services.agent_analysis_service import ensure_agent_consensus_for_active_symbols

    await asyncio.sleep(45)
    while True:
        try:
            await ensure_agent_consensus_for_active_symbols()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("agent_consensus_watch_error", error=str(exc))
        await asyncio.sleep(90)


async def _hourly_report_loop() -> None:
    while True:
        try:
            now = datetime.now(timezone.utc)
            wait = 3600 - (now.minute * 60 + now.second)
            if wait <= 0:
                wait = 3600
            await asyncio.sleep(wait)
            await publish_hourly_report()
            logger.info("hourly_report_published")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("hourly_report_loop_error", error=str(exc))
            await asyncio.sleep(60)


async def _feed_health_watch_loop() -> None:
    """Detect dead/stale feeds and restart them without full system reboot."""
    from app.services.feed_health_service import build_feed_status_payload, run_recovery_cycle

    await asyncio.sleep(settings.feed_startup_grace_seconds)
    while True:
        try:
            report = await run_recovery_cycle()
            feed_payload = await build_feed_status_payload()
            await broadcaster.broadcast_feed_status(feed_payload)
            if any(f.recovered for f in report.feeds):
                statuses = await build_all_market_statuses()
                payload = {
                    sym: status.model_dump(mode="json") for sym, status in statuses.items()
                }
                await broadcaster.broadcast_market_status(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("feed_health_watch_error", error=str(exc))
        await asyncio.sleep(settings.feed_health_interval_seconds)


async def _market_reopen_watch_loop() -> None:
    """Bootstrap data when scheduled markets transition closed → open."""
    global _market_was_open
    from app.feeds.history_bootstrap import bootstrap_asset

    for sym in symbols_with_scheduled_reopen():
        _market_was_open[sym] = is_market_open(sym)

    while True:
        try:
            for sym in symbols_with_scheduled_reopen():
                open_now = is_market_open(sym)
                was_open = _market_was_open.get(sym, False)
                if not was_open and open_now:
                    logger.info("market_opened_triggering_bootstrap", symbol=sym)
                    await bootstrap_asset(sym)
                _market_was_open[sym] = open_now
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("market_reopen_watch_error", error=str(exc))
            await asyncio.sleep(30)


async def _market_status_tick_loop() -> None:
    while True:
        try:
            statuses = await build_all_market_statuses()
            payload = {
                sym: status.model_dump(mode="json") for sym, status in statuses.items()
            }
            await broadcaster.broadcast_market_status(payload)
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("market_status_tick_error", error=str(exc))
            await asyncio.sleep(60)


async def _auto_outcome_tracker_loop() -> None:
    """Monitor open Telegram signals for TP/SL/expiry."""
    from app.database import AsyncSessionLocal
    from app.services.outcome_tracker import auto_outcome_tracker

    await asyncio.sleep(60)
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await auto_outcome_tracker.track_pending_outcomes(session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("auto_outcome_tracker_error", error=str(exc))
        await asyncio.sleep(300)


def start_background_tasks() -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(_hourly_report_loop(), name="hourly_report"),
        asyncio.create_task(_feed_health_watch_loop(), name="feed_health_watch"),
        asyncio.create_task(_market_status_tick_loop(), name="market_status_tick"),
        asyncio.create_task(_market_reopen_watch_loop(), name="market_reopen_watch"),
        asyncio.create_task(_agent_consensus_watch_loop(), name="agent_consensus_watch"),
        asyncio.create_task(_auto_outcome_tracker_loop(), name="auto_outcome_tracker"),
    ]
