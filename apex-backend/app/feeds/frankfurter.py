"""Frankfurter polling feed — free ECB rates for FX pairs (live + bootstrap)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.config import settings
from app.core.cache import set_feed_last_update, set_latest_price
from app.feeds.frankfurter_client import build_hourly_bar, fetch_latest_rate_with_source
from app.logging_config import logger
from app.services.feed_status import FeedConnectionState, set_feed_status
from app.services.market_data_store import fetch_bars_from_db

BarCallback = Callable[[dict[str, Any]], Awaitable[None]]


class FrankfurterFeed:
    def __init__(
        self,
        from_symbol: str = "EUR",
        to_symbol: str = "USD",
        apex_symbol: str = "EURUSD",
        poll_interval: int | None = None,
        on_bar: BarCallback | None = None,
        stagger_seconds: int = 0,
    ) -> None:
        self.from_symbol = from_symbol
        self.to_symbol = to_symbol
        self.apex_symbol = apex_symbol
        self.poll_interval = poll_interval or settings.frankfurter_poll_interval_seconds
        self.on_bar = on_bar
        self._stagger_seconds = stagger_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_success_at: datetime | None = None
        self._error_count = 0
        self._last_price: float | None = None
        self._active_hour: datetime | None = None
        self._active_bar: dict[str, Any] | None = None

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "symbol": self.apex_symbol,
            "feed_type": "frankfurter",
            "pair": f"{self.from_symbol}/{self.to_symbol}",
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done(),
            "last_success_at": self._last_success_at.isoformat() if self._last_success_at else None,
            "error_count": self._error_count,
            "reconnect_count": 0,
        }

    async def _poll_once(self) -> bool:
        rate, live_source = await fetch_latest_rate_with_source(
            self.from_symbol,
            self.to_symbol,
        )
        source = live_source or "db"
        now = datetime.now(timezone.utc)

        if rate is None:
            bars = await fetch_bars_from_db(self.apex_symbol, limit=1)
            if not bars:
                return False
            bar = dict(bars[-1])
            bar["source"] = "db"
            source = "db"
            logger.info("live_bar_db_fallback", symbol=self.apex_symbol)
        else:
            hour_ts = now.replace(minute=0, second=0, microsecond=0)
            if (
                self._active_hour is not None
                and hour_ts > self._active_hour
                and self._active_bar is not None
            ):
                closed_bar = dict(self._active_bar)
                closed_bar["is_closed"] = True
                await self._emit_bar(closed_bar, source, now)
                self._active_hour = None
                self._active_bar = None

            open_price = self._last_price if self._last_price is not None else rate
            high = max(open_price, rate)
            low = min(open_price, rate)
            bar = build_hourly_bar(
                apex_symbol=self.apex_symbol,
                price=rate,
                at=now,
                source=source,
                is_closed=False,
                open_price=open_price,
                high=high,
                low=low,
            )
            if self._active_hour == hour_ts and self._active_bar is not None:
                bar["open"] = self._active_bar["open"]
                bar["high"] = max(float(self._active_bar["high"]), rate)
                bar["low"] = min(float(self._active_bar["low"]), rate)
            self._active_hour = hour_ts
            self._active_bar = dict(bar)
            self._last_price = rate

        self._last_success_at = now
        self._error_count = 0
        await set_latest_price(bar["symbol"], bar["close"], bar["timestamp"])
        await set_feed_last_update(bar["symbol"], bar["timestamp"])
        await set_feed_status(
            self.apex_symbol,
            FeedConnectionState.CONNECTED,
            last_update=self._last_success_at,
            detail=f"source={source}",
        )
        if self.on_bar:
            await self.on_bar(bar)
        return True

    async def _emit_bar(self, bar: dict[str, Any], source: str, now: datetime) -> None:
        await set_latest_price(bar["symbol"], bar["close"], bar["timestamp"])
        await set_feed_last_update(bar["symbol"], bar["timestamp"])
        await set_feed_status(
            self.apex_symbol,
            FeedConnectionState.CONNECTED,
            last_update=now,
            detail=f"source={source}",
        )
        if self.on_bar:
            await self.on_bar(bar)

    async def _poll_loop(self) -> None:
        from app.services.market_hours import is_market_open

        error_backoff = 60
        if self._stagger_seconds > 0:
            await asyncio.sleep(self._stagger_seconds)

        while self._running:
            try:
                if not is_market_open(self.apex_symbol):
                    await asyncio.sleep(min(self.poll_interval, 300))
                    continue

                ok = await self._poll_once()
                if ok:
                    await asyncio.sleep(self.poll_interval)
                else:
                    await asyncio.sleep(min(error_backoff, 300))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._error_count += 1
                logger.error("frankfurter_poll_error", symbol=self.apex_symbol, error=str(exc))
                await set_feed_status(
                    self.apex_symbol,
                    FeedConnectionState.DISCONNECTED,
                    consecutive_failures=self._error_count,
                    detail=str(exc)[:120],
                )
                await asyncio.sleep(error_backoff)
                error_backoff = min(error_backoff * 2, 600)

    def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(),
            name=f"feed_frankfurter_{self.apex_symbol}",
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
        try:
            return await self._poll_once()
        except Exception as exc:
            logger.error("frankfurter_fetch_now_error", symbol=self.apex_symbol, error=str(exc))
            return False
