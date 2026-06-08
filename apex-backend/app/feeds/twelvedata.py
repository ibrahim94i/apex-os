"""TwelveData REST polling feed for gold (XAUUSD) with DB fallback."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.config import settings
from app.core.cache import set_feed_last_update, set_latest_price
from app.feeds.twelvedata_limiter import is_feed_recovery_paused
from app.logging_config import logger
from app.services.feed_status import FeedConnectionState, set_feed_status
from app.services.market_data_resolver import fetch_live_bar_with_fallback
from app.utils.time_utils import compute_age_seconds, parse_utc_timestamp

BarCallback = Callable[[dict[str, Any]], Awaitable[None]]


class TwelveDataFeed:
    def __init__(
        self,
        api_key: str | None = None,
        symbol: str | None = None,
        apex_symbol: str | None = None,
        interval: str = "1h",
        poll_interval: int = 300,
        on_bar: BarCallback | None = None,
        stagger_seconds: int = 0,
    ) -> None:
        from app.config import settings as app_settings

        self.api_key = api_key or app_settings.twelvedata_api_key
        self.symbol = symbol or app_settings.twelvedata_symbol
        self.apex_symbol = apex_symbol or self.symbol.replace("/", "")
        self.interval = interval
        self.poll_interval = poll_interval
        self.on_bar = on_bar
        self._stagger_seconds = stagger_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_success_at: datetime | None = None
        self._last_source: str | None = None
        self._error_count = 0
        self._reconnect_count = 0

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "symbol": self.apex_symbol,
            "feed_type": "twelvedata",
            "td_symbol": self.symbol,
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done(),
            "last_success_at": self._last_success_at.isoformat() if self._last_success_at else None,
            "last_source": self._last_source,
            "twelvedata_rate_limited": is_feed_recovery_paused(),
            "error_count": self._error_count,
            "reconnect_count": self._reconnect_count,
        }

    async def _publish_bar(self, bar: dict[str, Any], source: str) -> None:
        self._last_success_at = datetime.now(timezone.utc)
        self._last_source = source
        self._error_count = 0
        bar_dt = parse_utc_timestamp(bar["timestamp"])
        bar_age = compute_age_seconds(bar_dt)
        await set_latest_price(bar["symbol"], bar["close"], bar["timestamp"])
        await set_feed_last_update(
            bar["symbol"],
            bar["timestamp"],
            received_at=datetime.now(timezone.utc).isoformat(),
        )
        await set_feed_status(
            self.apex_symbol,
            FeedConnectionState.CONNECTED,
            last_update=bar_dt,
            age_seconds=bar_age,
            detail=f"source={source}",
        )
        if self.on_bar:
            await self.on_bar(bar)

    async def _poll_once(self) -> bool:
        bar, source = await fetch_live_bar_with_fallback(
            self.apex_symbol,
            self.symbol,
            interval=self.interval,
        )
        if not bar or not source:
            return False
        await self._publish_bar(bar, source)
        return True

    async def _poll_loop(self) -> None:
        from app.services.market_hours import is_market_open

        error_backoff = 5

        if self._stagger_seconds > 0:
            await asyncio.sleep(self._stagger_seconds)

        while self._running:
            try:
                if not is_market_open(self.apex_symbol):
                    logger.debug("twelvedata_market_closed", symbol=self.apex_symbol)
                    await asyncio.sleep(min(self.poll_interval, 60))
                    continue

                if await self._poll_once():
                    await asyncio.sleep(self.poll_interval)
                else:
                    self._error_count += 1
                    await set_feed_status(
                        self.apex_symbol,
                        FeedConnectionState.RECONNECTING,
                        consecutive_failures=self._error_count,
                    )
                    await asyncio.sleep(min(error_backoff, 60))
                    error_backoff = min(error_backoff * 2, 120)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._error_count += 1
                self._reconnect_count += 1
                await set_feed_status(
                    self.apex_symbol,
                    FeedConnectionState.DISCONNECTED,
                    consecutive_failures=self._error_count,
                    detail=str(exc)[:120],
                )
                logger.error(
                    "twelvedata_poll_error",
                    symbol=self.apex_symbol,
                    error=str(exc),
                    backoff=error_backoff,
                )
                await asyncio.sleep(error_backoff)
                error_backoff = min(error_backoff * 2, 120)

    def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(),
            name=f"feed_twelvedata_{self.apex_symbol}",
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def fetch_now(self) -> bool:
        """Immediate poll — used during recovery."""
        try:
            return await self._poll_once()
        except Exception as exc:
            logger.error("twelvedata_fetch_now_error", symbol=self.apex_symbol, error=str(exc))
            return False
