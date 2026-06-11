"""Binance futures H1 kline WebSocket — works on Railway where REST returns 451."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

from app.core.cache import set_feed_last_update, set_latest_price
from app.logging_config import logger
from app.services.feed_status import FeedConnectionState, set_feed_status
from app.utils.volume_policy import apply_volume_policy_to_bar

BarCallback = Callable[[dict[str, Any]], Awaitable[None]]


def parse_futures_kline_message(
    message: str,
    *,
    binance_symbol: str,
    apex_symbol: str,
) -> dict[str, Any] | None:
    data = json.loads(message)
    kline = data.get("k", {})
    if not kline:
        return None
    symbol = str(kline.get("s", "")).upper()
    if symbol and symbol != binance_symbol.upper():
        return None
    return apply_volume_policy_to_bar(
        {
            "symbol": apex_symbol,
            "timestamp": datetime.fromtimestamp(
                kline["t"] / 1000,
                tz=timezone.utc,
            ).isoformat(),
            "open": float(kline["o"]),
            "high": float(kline["h"]),
            "low": float(kline["l"]),
            "close": float(kline["c"]),
            "volume": float(kline["v"]),
            "source": "binance",
            "is_closed": bool(kline.get("x", False)),
        }
    )


class BinanceFuturesKlineWsFeed:
    """Streams Binance futures XAUUSDT H1 klines into the agent pipeline."""

    def __init__(
        self,
        *,
        ws_url: str,
        binance_symbol: str,
        apex_symbol: str,
        twelvedata_symbol: str | None = None,
        on_bar: BarCallback | None = None,
    ) -> None:
        self.ws_url = ws_url
        self.binance_symbol = binance_symbol
        self.apex_symbol = apex_symbol
        self.twelvedata_symbol = twelvedata_symbol
        self.on_bar = on_bar
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_message_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_source: str | None = None
        self._reconnect_count = 0

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "symbol": self.apex_symbol,
            "feed_type": "binance",
            "binance_symbol": self.binance_symbol,
            "binance_market": "futures",
            "api": "ws_kline_1h",
            "twelvedata_fallback": self.twelvedata_symbol,
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done(),
            "last_message_at": self._last_message_at.isoformat() if self._last_message_at else None,
            "last_success_at": self._last_success_at.isoformat() if self._last_success_at else None,
            "last_source": self._last_source,
            "reconnect_count": self._reconnect_count,
            "error_count": 0,
        }

    async def _publish_bar(self, bar: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        self._last_message_at = now
        self._last_success_at = now
        self._last_source = bar.get("source", "binance")
        await set_latest_price(bar["symbol"], bar["close"], now.isoformat())
        await set_feed_last_update(bar["symbol"], bar["timestamp"], received_at=now.isoformat())
        await set_feed_status(
            self.apex_symbol,
            FeedConnectionState.CONNECTED,
            last_update=now,
            detail=f"source={self._last_source}",
        )
        if self.on_bar:
            await self.on_bar(bar)

    async def _handle_message(self, message: str) -> None:
        try:
            bar = parse_futures_kline_message(
                message,
                binance_symbol=self.binance_symbol,
                apex_symbol=self.apex_symbol,
            )
            if not bar:
                return
            await self._publish_bar(bar)
        except Exception as exc:
            logger.error(
                "binance_futures_kline_ws_message_error",
                apex_symbol=self.apex_symbol,
                error=str(exc),
            )

    async def _connect_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                logger.info(
                    "binance_futures_kline_ws_connecting",
                    apex_symbol=self.apex_symbol,
                    url=self.ws_url,
                )
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    backoff = 1
                    self._reconnect_count = 0
                    logger.info("binance_futures_kline_ws_connected", apex_symbol=self.apex_symbol)
                    await set_feed_status(self.apex_symbol, FeedConnectionState.CONNECTED)
                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(message)
            except ConnectionClosed as exc:
                logger.warning(
                    "binance_futures_kline_ws_disconnected",
                    apex_symbol=self.apex_symbol,
                    code=exc.code,
                    reason=str(exc.reason),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "binance_futures_kline_ws_error",
                    apex_symbol=self.apex_symbol,
                    error=str(exc),
                )

            if self._running:
                self._reconnect_count += 1
                await set_feed_status(
                    self.apex_symbol,
                    FeedConnectionState.RECONNECTING,
                    detail=f"attempt_{self._reconnect_count}",
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._connect_loop(),
            name=f"feed_binance_futures_kline_{self.apex_symbol}",
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
        from app.services.market_data_resolver import fetch_live_bar_with_fallback

        bar, source = await fetch_live_bar_with_fallback(
            self.apex_symbol,
            self.twelvedata_symbol,
            interval="1h",
        )
        if not bar or not source:
            return False
        await self._publish_bar(bar)
        return True
