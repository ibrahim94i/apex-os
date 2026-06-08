"""Feed health monitoring, auto-recovery, and missed-data backfill."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.config.assets import ACTIVE_SYMBOLS, get_asset
from app.core.cache import get_feed_last_update, get_latest_price, get_latest_regime
from app.feeds.manager import feed_manager
from app.feeds.twelvedata_limiter import (
    feed_recovery_pause_remaining_seconds,
    is_feed_recovery_paused,
)
from app.logging_config import logger
from app.services.feed_status import FeedConnectionState, get_all_feed_statuses, set_feed_status
from app.services.market_hours import is_market_open
from app.services.feed_freshness import (
    feed_poll_age_seconds,
    feed_staleness_limit_seconds,
    is_feed_poll_stale,
)
from app.utils.time_utils import parse_utc_timestamp

_recovery_trackers: dict[str, "_RecoveryTracker"] = {}
_app_started_at: datetime = datetime.now(timezone.utc)


def mark_app_started() -> None:
    """Reset startup clock (called from lifespan)."""
    global _app_started_at
    _app_started_at = datetime.now(timezone.utc)


@dataclass
class _RecoveryTracker:
    consecutive_failures: int = 0
    cooldown_until: datetime | None = None


@dataclass
class FeedHealthStatus:
    symbol: str
    feed_type: str
    market_open: bool
    feed_running: bool
    connection_status: str
    connection_status_ar: str
    last_update: datetime | None = None
    stale: bool = False
    age_seconds: int | None = None
    consecutive_failures: int = 0
    recovered: bool = False
    in_cooldown: bool = False


@dataclass
class FeedHealthReport:
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    feeds: list[FeedHealthStatus] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def _parse_ts(raw: str) -> datetime:
    return parse_utc_timestamp(raw)


def _tracker(symbol: str) -> _RecoveryTracker:
    if symbol not in _recovery_trackers:
        _recovery_trackers[symbol] = _RecoveryTracker()
    return _recovery_trackers[symbol]


async def _feed_data_age_seconds(symbol: str) -> int | None:
    last_raw = await get_feed_last_update(symbol)
    return feed_poll_age_seconds(last_raw)


async def _is_feed_data_fresh(symbol: str) -> bool:
    age = await _feed_data_age_seconds(symbol)
    if age is None:
        return False
    return age <= feed_staleness_limit_seconds(symbol)


async def check_feed_health(symbol: str) -> FeedHealthStatus:
    asset = get_asset(symbol)
    feed_type = asset.feed_type if asset else "unknown"
    open_now = is_market_open(symbol)
    running = feed_manager.is_running(symbol)
    tracker = _tracker(symbol)

    last_raw = await get_feed_last_update(symbol)
    last_dt: datetime | None = None
    age: int | None = None
    stale = False

    startup_age = int((datetime.now(timezone.utc) - _app_started_at).total_seconds())
    in_startup_grace = startup_age < settings.feed_startup_grace_seconds
    price_data = await get_latest_price(symbol)
    regime_data = await get_latest_regime(symbol)
    has_warm_data = price_data is not None and regime_data is not None

    if last_raw:
        poll_ts_raw = last_raw.get("received_at") or last_raw.get("timestamp")
        if poll_ts_raw:
            last_dt = _parse_ts(poll_ts_raw)
        age = feed_poll_age_seconds(last_raw)
        limit = feed_staleness_limit_seconds(symbol)
        if open_now and age is not None and age > limit:
            stale = True
        elif open_now and age is not None and age > settings.feed_disconnect_threshold_seconds:
            stale = True
    elif open_now and not in_startup_grace and not has_warm_data:
        stale = True

    if not running and open_now:
        stale = True

    in_cooldown = bool(
        tracker.cooldown_until and datetime.now(timezone.utc) < tracker.cooldown_until
    )

    if stale and open_now and not in_cooldown:
        conn = FeedConnectionState.DISCONNECTED
    elif in_cooldown:
        conn = FeedConnectionState.RECONNECTING
    elif running and not stale:
        conn = FeedConnectionState.CONNECTED
    elif not open_now:
        conn = FeedConnectionState.CONNECTED if running else FeedConnectionState.DISCONNECTED
    else:
        conn = FeedConnectionState.RECONNECTING

    from app.services.feed_status import STATUS_AR

    return FeedHealthStatus(
        symbol=symbol,
        feed_type=feed_type,
        market_open=open_now,
        feed_running=running,
        connection_status=conn.value,
        connection_status_ar=STATUS_AR[conn.value],
        last_update=last_dt,
        stale=stale,
        age_seconds=age,
        consecutive_failures=tracker.consecutive_failures,
        in_cooldown=in_cooldown,
    )


async def recover_feed(symbol: str, reason: str) -> bool:
    """Restart feed, backfill missed bars, reset on success."""
    tracker = _tracker(symbol)
    now = datetime.now(timezone.utc)

    if tracker.cooldown_until and now < tracker.cooldown_until:
        logger.info("feed_recovery_skipped_cooldown", symbol=symbol)
        return False

    if is_feed_recovery_paused():
        logger.info(
            "feed_recovery_skipped_twelvedata_429",
            symbol=symbol,
            remaining_seconds=feed_recovery_pause_remaining_seconds(),
        )
        return False

    await set_feed_status(
        symbol,
        FeedConnectionState.RECONNECTING,
        consecutive_failures=tracker.consecutive_failures,
        detail=reason,
    )
    logger.warning("feed_recovery_start", symbol=symbol, reason=reason)

    try:
        await feed_manager.restart_feed(symbol)
        feed = feed_manager.get_feed(symbol)
        if feed and hasattr(feed, "fetch_now"):
            await feed.fetch_now()

        from app.feeds.history_bootstrap import bootstrap_asset

        if await _is_feed_data_fresh(symbol):
            ok = True
            logger.info("feed_recovery_fresh_after_restart", symbol=symbol)
        else:
            logger.warning(
                "feed_recovery_stale_after_restart",
                symbol=symbol,
                age_seconds=await _feed_data_age_seconds(symbol),
            )
            from app.feeds.history_bootstrap import bootstrap_limit_for, bootstrap_success_threshold
            from app.services.market_data_store import count_bars_in_db

            asset = get_asset(symbol)
            bar_limit = bootstrap_limit_for(asset) if asset else 250
            threshold = bootstrap_success_threshold(asset, bar_limit) if asset else 50
            db_count = await count_bars_in_db(symbol)
            if db_count >= threshold:
                ok = True
                logger.info(
                    "feed_recovery_skipped_bootstrap_db_sufficient",
                    symbol=symbol,
                    db_bars=db_count,
                    threshold=threshold,
                )
            else:
                ok = await bootstrap_asset(symbol)

        if ok and not await _is_feed_data_fresh(symbol):
            price_data = await get_latest_price(symbol)
            ok = price_data is not None
            if ok:
                logger.info(
                    "feed_recovery_accepted_db_warm",
                    symbol=symbol,
                    age_seconds=await _feed_data_age_seconds(symbol),
                )

        if ok:
            tracker.consecutive_failures = 0
            tracker.cooldown_until = None
            last_raw = await get_feed_last_update(symbol)
            last_dt = (
                _parse_ts(last_raw["timestamp"])
                if last_raw and last_raw.get("timestamp")
                else datetime.now(timezone.utc)
            )
            await set_feed_status(
                symbol,
                FeedConnectionState.CONNECTED,
                last_update=last_dt,
                age_seconds=await _feed_data_age_seconds(symbol),
                consecutive_failures=0,
            )
            try:
                from app.core.cache import get_agent_consensus
                from app.services.agent_analysis_service import run_agent_analysis

                if not await get_agent_consensus(symbol):
                    await run_agent_analysis(symbol)
            except Exception as agent_exc:
                logger.warning(
                    "feed_recovery_agent_refresh_failed",
                    symbol=symbol,
                    error=str(agent_exc),
                )
            logger.info("feed_recovery_complete", symbol=symbol)
            return True

        raise RuntimeError("feed_still_stale_after_recovery")

    except Exception as exc:
        tracker.consecutive_failures += 1
        logger.error(
            "feed_recovery_failed",
            symbol=symbol,
            error=str(exc),
            failures=tracker.consecutive_failures,
        )
        if tracker.consecutive_failures >= settings.feed_max_consecutive_failures:
            tracker.cooldown_until = now + timedelta(
                seconds=settings.feed_recovery_cooldown_seconds
            )
            logger.warning(
                "feed_recovery_cooldown",
                symbol=symbol,
                seconds=settings.feed_recovery_cooldown_seconds,
            )
        await set_feed_status(
            symbol,
            FeedConnectionState.DISCONNECTED,
            consecutive_failures=tracker.consecutive_failures,
            detail=str(exc),
        )
        return False


async def run_recovery_cycle(*, force: bool = False) -> FeedHealthReport:
    """Check all feeds; auto-reconnect if disconnected > threshold."""
    report = FeedHealthReport()
    recovery_paused = is_feed_recovery_paused()
    if recovery_paused:
        logger.info(
            "feed_recovery_paused_twelvedata_429",
            remaining_seconds=feed_recovery_pause_remaining_seconds(),
        )

    for symbol in ACTIVE_SYMBOLS:
        status = await check_feed_health(symbol)
        needs_recovery = False
        reason = ""

        if not status.feed_running and status.market_open:
            needs_recovery = True
            reason = "feed_task_not_running"
        elif status.stale and status.market_open and not status.in_cooldown:
            needs_recovery = True
            reason = "data_stale"
        elif (
            status.feed_running
            and status.market_open
            and not status.in_cooldown
            and status.age_seconds is not None
            and status.age_seconds > feed_staleness_limit_seconds(symbol)
        ):
            needs_recovery = True
            reason = "data_stale_over_limit"
        elif force and status.market_open and not status.in_cooldown:
            regime = await get_latest_regime(symbol)
            if status.stale or regime is None:
                needs_recovery = True
                reason = "forced_recovery"

        if needs_recovery and status.market_open and not status.in_cooldown:
            if recovery_paused:
                report.actions.append(f"{symbol}:twelvedata_429_pause")
            else:
                recovered = await recover_feed(symbol, reason)
                status.recovered = recovered
                status = await check_feed_health(symbol)
                report.actions.append(f"{symbol}:{reason}:{'ok' if recovered else 'fail'}")
        elif needs_recovery and status.in_cooldown:
            report.actions.append(f"{symbol}:cooldown_wait")
        elif not status.market_open:
            await set_feed_status(
                symbol,
                FeedConnectionState.CONNECTED if status.feed_running else FeedConnectionState.DISCONNECTED,
                age_seconds=status.age_seconds,
            )
        elif status.feed_running and not status.stale:
            await set_feed_status(
                symbol,
                FeedConnectionState.CONNECTED,
                last_update=status.last_update,
                poll_received_at=status.last_update,
                age_seconds=status.age_seconds,
            )

        report.feeds.append(status)

    if report.actions:
        logger.info("feed_health_cycle", actions=report.actions)

    return report


async def build_feed_status_payload() -> dict[str, dict]:
    return await get_all_feed_statuses(ACTIVE_SYMBOLS)
