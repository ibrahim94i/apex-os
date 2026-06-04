"""TwelveData REST polling feed with error backoff and auto-recovery."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from app.config import settings
from app.core.cache import set_feed_last_update, set_latest_price
from app.logging_config import logger
from app.services.feed_status import FeedConnectionState, set_feed_status

BarCallback = Callable[[dict[str, Any]], Awaitable[None]]

# Max age for latest bar before considered stale (interval-aware)
_INTERVAL_MAX_BAR_AGE: dict[str, float] = {
    "1h": 3900.0,    # current H1 bar can be up to ~60 min old
    "30min": 2100.0,
    "15min": 1200.0,
    "5min": 600.0,
    "1min": 180.0,
}


class TwelveDataFeed:
    BASE_URL = "https://api.twelvedata.com/time_series"

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
        self.api_key = api_key or settings.twelvedata_api_key
        self.symbol = symbol or settings.twelvedata_symbol
        self.apex_symbol = apex_symbol or self.symbol.replace("/", "")
        self.interval = interval
        self.poll_interval = poll_interval
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
            "feed_type": "twelvedata",
            "td_symbol": self.symbol,
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done(),
            "last_success_at": self._last_success_at.isoformat() if self._last_success_at else None,
            "error_count": self._error_count,
            "reconnect_count": self._reconnect_count,
        }

    def _bar_age_seconds(self, bar: dict[str, Any]) -> float:
        ts = bar["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())

    def _max_bar_age_seconds(self) -> float:
        return _INTERVAL_MAX_BAR_AGE.get(
            self.interval, float(settings.feed_staleness_limit_seconds)
        )

    def _is_bar_stale(self, bar: dict[str, Any]) -> bool:
        # Hourly candles are NOT stale just because the bar opened <1h ago
        return self._bar_age_seconds(bar) > self._max_bar_age_seconds()

    async def _fetch_latest_bar(self) -> dict[str, Any] | None:
        if not self.api_key or self.api_key == "your_key_here":
            logger.warning("twelvedata_api_key_not_configured", symbol=self.apex_symbol)
            return None

        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "outputsize": 1,
            "apikey": self.api_key,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            from app.feeds.twelvedata_limiter import throttled_get

            response = await throttled_get(client, self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("status") == "error":
            raise RuntimeError(data.get("message", "twelvedata error"))

        if "values" not in data or not data["values"]:
            logger.warning("twelvedata_no_data", symbol=self.apex_symbol, response=data)
            return None

        row = data["values"][0]
        ts = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

        return {
            "symbol": self.apex_symbol,
            "timestamp": ts.isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
            "source": "twelvedata",
            "is_closed": True,
        }

    async def _fetch_latest_bar_with_retry(self) -> dict[str, Any] | None:
        """Fetch latest bar; retry automatically when TwelveData returns stale data."""
        max_retries = settings.twelvedata_stale_retry_count
        delay = settings.twelvedata_stale_retry_delay_seconds
        last_bar: dict[str, Any] | None = None

        for attempt in range(1, max_retries + 2):
            try:
                bar = await self._fetch_latest_bar()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    logger.warning(
                        "twelvedata_rate_limited_skip_retry",
                        symbol=self.apex_symbol,
                        attempt=attempt,
                    )
                    return None
                raise
            if bar is None:
                if attempt <= max_retries:
                    logger.info(
                        "twelvedata_empty_retry",
                        symbol=self.apex_symbol,
                        attempt=attempt,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return None

            last_bar = bar
            if not self._is_bar_stale(bar):
                if attempt > 1:
                    logger.info(
                        "twelvedata_stale_retry_success",
                        symbol=self.apex_symbol,
                        attempt=attempt,
                    )
                return bar

            logger.warning(
                "twelvedata_stale_data_retry",
                symbol=self.apex_symbol,
                bar_age_seconds=round(self._bar_age_seconds(bar), 1),
                attempt=attempt,
                max_retries=max_retries,
            )
            if attempt <= max_retries:
                await asyncio.sleep(delay)

        return last_bar

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

                bar = await self._fetch_latest_bar_with_retry()
                if bar:
                    self._last_success_at = datetime.now(timezone.utc)
                    self._error_count = 0
                    error_backoff = 5
                    bar_ts = bar["timestamp"]
                    if isinstance(bar_ts, str):
                        bar_dt = datetime.fromisoformat(bar_ts.replace("Z", "+00:00"))
                    else:
                        bar_dt = bar_ts
                    if bar_dt.tzinfo is None:
                        bar_dt = bar_dt.replace(tzinfo=timezone.utc)
                    bar_age = int((datetime.now(timezone.utc) - bar_dt).total_seconds())
                    await set_latest_price(bar["symbol"], bar["close"], bar["timestamp"])
                    await set_feed_last_update(bar["symbol"], bar["timestamp"])
                    await set_feed_status(
                        self.apex_symbol,
                        FeedConnectionState.CONNECTED,
                        last_update=bar_dt,
                        age_seconds=bar_age,
                    )
                    if self.on_bar:
                        await self.on_bar(bar)
                    await asyncio.sleep(self.poll_interval)
                else:
                    await asyncio.sleep(min(error_backoff, 60))

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
                if exc.response.status_code == 429:
                    error_backoff = max(error_backoff, 90)
                logger.error(
                    "twelvedata_poll_error",
                    symbol=self.apex_symbol,
                    status=exc.response.status_code,
                    error=str(exc),
                    backoff=error_backoff,
                )
                await asyncio.sleep(error_backoff)
                error_backoff = min(error_backoff * 2, 180)
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
            bar = await self._fetch_latest_bar_with_retry()
            if not bar:
                return False
            self._last_success_at = datetime.now(timezone.utc)
            bar_ts = bar["timestamp"]
            if isinstance(bar_ts, str):
                bar_dt = datetime.fromisoformat(bar_ts.replace("Z", "+00:00"))
            else:
                bar_dt = bar_ts
            if bar_dt.tzinfo is None:
                bar_dt = bar_dt.replace(tzinfo=timezone.utc)
            bar_age = int((datetime.now(timezone.utc) - bar_dt).total_seconds())
            await set_latest_price(bar["symbol"], bar["close"], bar["timestamp"])
            await set_feed_last_update(bar["symbol"], bar["timestamp"])
            await set_feed_status(
                self.apex_symbol,
                FeedConnectionState.CONNECTED,
                last_update=bar_dt,
                age_seconds=bar_age,
            )
            if self.on_bar:
                await self.on_bar(bar)
            return True
        except Exception as exc:
            logger.error("twelvedata_fetch_now_error", symbol=self.apex_symbol, error=str(exc))
            return False
