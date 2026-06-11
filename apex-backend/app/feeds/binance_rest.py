"""Binance REST klines polling feed — free public API, no key."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.core.cache import set_feed_last_update, set_latest_price
from app.logging_config import logger
from app.services.feed_status import FeedConnectionState, set_feed_status

BarCallback = Callable[[dict[str, Any]], Awaitable[None]]


class BinanceRestFeed:
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        apex_symbol: str | None = None,
        binance_symbol: str | None = None,
        binance_market: str = "spot",
        twelvedata_symbol: str | None = None,
        interval: str = "1h",
        poll_interval: int = 180,
        on_bar: BarCallback | None = None,
        stagger_seconds: int = 0,
    ) -> None:
        self.symbol = symbol
        self.apex_symbol = apex_symbol or symbol
        self.binance_symbol = binance_symbol or symbol
        self.binance_market = binance_market  # type: ignore[assignment]
        self.twelvedata_symbol = twelvedata_symbol
        self.interval = interval
        self.poll_interval = poll_interval
        self.on_bar = on_bar
        self._stagger_seconds = stagger_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_success_at: datetime | None = None
        self._last_source: str | None = None
        self._error_count = 0

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "symbol": self.apex_symbol,
            "feed_type": "binance",
            "binance_symbol": self.binance_symbol,
            "binance_market": self.binance_market,
            "twelvedata_fallback": self.twelvedata_symbol,
            "api": "rest_klines",
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done(),
            "last_success_at": self._last_success_at.isoformat() if self._last_success_at else None,
            "last_source": self._last_source,
            "error_count": self._error_count,
            "reconnect_count": 0,
        }

    async def _poll_once(self) -> bool:
        from app.services.market_data_resolver import fetch_live_bar_with_fallback

        bar, source = await fetch_live_bar_with_fallback(
            self.apex_symbol,
            self.twelvedata_symbol,
            interval=self.interval,
        )
        if not bar or not source:
            await set_feed_status(
                self.apex_symbol,
                FeedConnectionState.DISCONNECTED,
                detail="all_sources_failed",
            )
            return False

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        self._last_success_at = now
        self._error_count = 0
        self._last_source = source
        await set_latest_price(bar["symbol"], bar["close"], now_iso)
        await set_feed_last_update(bar["symbol"], bar["timestamp"], received_at=now_iso)
        await set_feed_status(
            self.apex_symbol,
            FeedConnectionState.CONNECTED,
            last_update=now,
            poll_received_at=now,
            detail=f"source={source}",
        )
        if self.on_bar:
            await self.on_bar(bar)
        return True

    async def _poll_loop(self) -> None:
        error_backoff = 60
        if self._stagger_seconds > 0:
            await asyncio.sleep(self._stagger_seconds)

        while self._running:
            try:
                ok = await self._poll_once()
                if ok:
                    await asyncio.sleep(self.poll_interval)
                else:
                    await asyncio.sleep(min(error_backoff, 300))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._error_count += 1
                logger.error("binance_rest_poll_error", symbol=self.apex_symbol, error=str(exc))
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
            name=f"feed_binance_rest_{self.apex_symbol}",
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
            logger.error("binance_rest_fetch_now_error", symbol=self.apex_symbol, error=str(exc))
            return False
