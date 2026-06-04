"""Alpha Vantage FX polling feed — optional FX source (not used for active symbols)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from app.config import settings
from app.core.cache import set_feed_last_update, set_latest_price
from app.feeds.alphavantage_client import fetch_fx_intraday_bars
from app.logging_config import logger
from app.services.feed_status import FeedConnectionState, set_feed_status

BarCallback = Callable[[dict[str, Any]], Awaitable[None]]

_INTERVAL_MAX_BAR_AGE: dict[str, float] = {
    "1h": 3900.0,
    "60min": 3900.0,
}


class AlphaVantageFeed:
    def __init__(
        self,
        api_key: str | None = None,
        from_symbol: str = "EUR",
        to_symbol: str = "USD",
        apex_symbol: str = "EURUSD",
        interval: str = "1h",
        poll_interval: int | None = None,
        on_bar: BarCallback | None = None,
        stagger_seconds: int = 0,
    ) -> None:
        self.api_key = api_key or settings.alphavantage_api_key
        self.from_symbol = from_symbol
        self.to_symbol = to_symbol
        self.apex_symbol = apex_symbol
        self.interval = interval
        self.poll_interval = poll_interval or settings.alphavantage_poll_interval_seconds
        self.on_bar = on_bar
        self._stagger_seconds = stagger_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_success_at: datetime | None = None
        self._error_count = 0
        self._reconnect_count = 0

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "symbol": self.apex_symbol,
            "feed_type": "alphavantage",
            "av_pair": f"{self.from_symbol}/{self.to_symbol}",
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done(),
            "last_success_at": self._last_success_at.isoformat() if self._last_success_at else None,
            "error_count": self._error_count,
            "reconnect_count": self._reconnect_count,
        }

    def _max_bar_age_seconds(self) -> float:
        return _INTERVAL_MAX_BAR_AGE.get(
            self.interval,
            _INTERVAL_MAX_BAR_AGE.get("1h", 3900.0),
        )

    def _is_bar_stale(self, bar: dict[str, Any]) -> bool:
        ts = bar["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > self._max_bar_age_seconds()

    async def _fetch_latest_bar(self) -> dict[str, Any] | None:
        bars = await fetch_fx_intraday_bars(
            from_symbol=self.from_symbol,
            to_symbol=self.to_symbol,
            apex_symbol=self.apex_symbol,
            interval=self.interval,
            outputsize="compact",
            api_key=self.api_key,
        )
        if not bars:
            return None
        return bars[-1]

    async def _poll_loop(self) -> None:
        from app.services.market_hours import is_market_open

        error_backoff = 60

        if self._stagger_seconds > 0:
            await asyncio.sleep(self._stagger_seconds)

        while self._running:
            try:
                if not is_market_open(self.apex_symbol):
                    logger.debug("alphavantage_market_closed", symbol=self.apex_symbol)
                    await asyncio.sleep(min(self.poll_interval, 300))
                    continue

                bar = await self._fetch_latest_bar()
                if bar and not self._is_bar_stale(bar):
                    self._last_success_at = datetime.now(timezone.utc)
                    self._error_count = 0
                    error_backoff = 60
                    await set_latest_price(bar["symbol"], bar["close"], bar["timestamp"])
                    await set_feed_last_update(bar["symbol"], bar["timestamp"])
                    await set_feed_status(
                        self.apex_symbol,
                        FeedConnectionState.CONNECTED,
                        last_update=self._last_success_at,
                    )
                    if self.on_bar:
                        await self.on_bar(bar)
                    await asyncio.sleep(self.poll_interval)
                elif bar:
                    logger.warning(
                        "alphavantage_stale_bar",
                        symbol=self.apex_symbol,
                        timestamp=bar["timestamp"],
                    )
                    await asyncio.sleep(min(error_backoff, 300))
                else:
                    await asyncio.sleep(min(error_backoff, 300))

            except asyncio.CancelledError:
                raise
            except httpx.HTTPStatusError as exc:
                self._error_count += 1
                self._reconnect_count += 1
                await set_feed_status(
                    self.apex_symbol,
                    FeedConnectionState.RECONNECTING,
                    consecutive_failures=self._error_count,
                )
                logger.error(
                    "alphavantage_poll_error",
                    symbol=self.apex_symbol,
                    status=exc.response.status_code,
                    error=str(exc),
                )
                await asyncio.sleep(error_backoff)
                error_backoff = min(error_backoff * 2, 3600)
            except Exception as exc:
                self._error_count += 1
                self._reconnect_count += 1
                msg = str(exc)
                if "premium" in msg.lower() or "call frequency" in msg.lower():
                    error_backoff = max(error_backoff, 3600)
                await set_feed_status(
                    self.apex_symbol,
                    FeedConnectionState.DISCONNECTED,
                    consecutive_failures=self._error_count,
                    detail=msg[:120],
                )
                logger.error(
                    "alphavantage_poll_error",
                    symbol=self.apex_symbol,
                    error=msg,
                    backoff=error_backoff,
                )
                await asyncio.sleep(error_backoff)
                error_backoff = min(error_backoff * 2, 3600)

    def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(),
            name=f"feed_alphavantage_{self.apex_symbol}",
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
            bar = await self._fetch_latest_bar()
            if not bar:
                return False
            self._last_success_at = datetime.now(timezone.utc)
            await set_latest_price(bar["symbol"], bar["close"], bar["timestamp"])
            await set_feed_last_update(bar["symbol"], bar["timestamp"])
            await set_feed_status(self.apex_symbol, FeedConnectionState.CONNECTED)
            if self.on_bar:
                await self.on_bar(bar)
            return True
        except Exception as exc:
            logger.error("alphavantage_fetch_now_error", symbol=self.apex_symbol, error=str(exc))
            return False
