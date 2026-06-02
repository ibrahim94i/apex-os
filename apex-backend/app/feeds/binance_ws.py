"""Binance WebSocket kline feed with auto-reconnect."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

from app.config import settings
from app.core.cache import set_feed_last_update, set_latest_price
from app.logging_config import logger
from app.services.feed_status import FeedConnectionState, set_feed_status

BarCallback = Callable[[dict[str, Any]], Awaitable[None]]


class BinanceWebSocketFeed:
    def __init__(
        self,
        ws_url: str | None = None,
        on_bar: BarCallback | None = None,
        apex_symbol: str = "BTCUSDT",
    ) -> None:
        self.ws_url = ws_url or settings.binance_ws_url
        self.on_bar = on_bar
        self.apex_symbol = apex_symbol
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_message_at: datetime | None = None
        self._reconnect_count = 0

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "symbol": self.apex_symbol,
            "feed_type": "binance",
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done(),
            "last_message_at": self._last_message_at.isoformat() if self._last_message_at else None,
            "reconnect_count": self._reconnect_count,
        }

    async def _handle_message(self, message: str) -> None:
        try:
            data = json.loads(message)
            kline = data.get("k", {})
            if not kline:
                return

            symbol = kline.get("s", self.apex_symbol)
            bar = {
                "symbol": symbol,
                "timestamp": datetime.fromtimestamp(
                    kline["t"] / 1000, tz=timezone.utc
                ).isoformat(),
                "open": float(kline["o"]),
                "high": float(kline["h"]),
                "low": float(kline["l"]),
                "close": float(kline["c"]),
                "volume": float(kline["v"]),
                "source": "binance",
                "is_closed": kline.get("x", False),
            }

            self._last_message_at = datetime.now(timezone.utc)
            await set_latest_price(bar["symbol"], bar["close"], bar["timestamp"])
            await set_feed_last_update(bar["symbol"], bar["timestamp"])
            await set_feed_status(
                bar["symbol"],
                FeedConnectionState.CONNECTED,
                last_update=self._last_message_at,
            )

            if self.on_bar:
                await self.on_bar(bar)

        except Exception as exc:
            logger.error("binance_ws_message_error", symbol=self.apex_symbol, error=str(exc))

    async def _connect_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                logger.info("binance_ws_connecting", symbol=self.apex_symbol, url=self.ws_url)
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    backoff = 1
                    logger.info("binance_ws_connected", symbol=self.apex_symbol)
                    await set_feed_status(self.apex_symbol, FeedConnectionState.CONNECTED)
                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(message)
            except ConnectionClosed as exc:
                logger.warning(
                    "binance_ws_disconnected",
                    symbol=self.apex_symbol,
                    code=exc.code,
                    reason=str(exc.reason),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("binance_ws_error", symbol=self.apex_symbol, error=str(exc))

            if self._running:
                self._reconnect_count += 1
                await set_feed_status(
                    self.apex_symbol,
                    FeedConnectionState.RECONNECTING,
                    detail=f"attempt_{self._reconnect_count}",
                )
                logger.info(
                    "binance_ws_reconnecting",
                    symbol=self.apex_symbol,
                    backoff=backoff,
                    attempt=self._reconnect_count,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._connect_loop(),
            name=f"feed_binance_{self.apex_symbol}",
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
