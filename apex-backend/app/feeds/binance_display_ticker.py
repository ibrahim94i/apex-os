"""Binance display price feed — dashboard only (no agents/signals)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from app.config import settings
from app.core.cache import set_display_price
from app.logging_config import logger
from app.websocket.manager import broadcaster


def parse_display_ticker_message(message: str, *, binance_symbol: str = "XAUUSDT") -> dict[str, Any] | None:
    """Parse Binance miniTicker, markPrice, or bookTicker payloads."""
    data = json.loads(message)
    symbol = str(data.get("s", "")).upper()
    if symbol and symbol != binance_symbol.upper():
        return None

    price_raw: Any = data.get("c") or data.get("p")
    if price_raw is None and data.get("e") == "bookTicker":
        try:
            bid = float(data.get("b", 0))
            ask = float(data.get("a", 0))
        except (TypeError, ValueError):
            bid = ask = 0.0
        if bid > 0 and ask > 0:
            price_raw = (bid + ask) / 2
        elif ask > 0:
            price_raw = ask
        elif bid > 0:
            price_raw = bid

    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    event_time = data.get("E") or data.get("T")
    if isinstance(event_time, (int, float)) and event_time > 0:
        timestamp = datetime.fromtimestamp(event_time / 1000, tz=timezone.utc).isoformat()
    else:
        timestamp = datetime.now(timezone.utc).isoformat()
    return {"price": price, "timestamp": timestamp}


def parse_rest_ticker_payload(payload: dict[str, Any], *, binance_symbol: str = "XAUUSDT") -> dict[str, Any] | None:
    symbol = str(payload.get("symbol", "")).upper()
    if symbol and symbol != binance_symbol.upper():
        return None
    try:
        price = float(payload.get("price", 0))
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    event_time = payload.get("time")
    if isinstance(event_time, (int, float)) and event_time > 0:
        timestamp = datetime.fromtimestamp(event_time / 1000, tz=timezone.utc).isoformat()
    else:
        timestamp = datetime.now(timezone.utc).isoformat()
    return {"price": price, "timestamp": timestamp}


class BinanceDisplayTickerFeed:
    """Streams Binance XAUUSDT (futures) for XAUUSD dashboard display only."""

    def __init__(
        self,
        *,
        apex_symbol: str = "XAUUSD",
        binance_symbol: str = "XAUUSDT",
        ws_url: str | None = None,
        rest_url: str | None = None,
    ) -> None:
        self.apex_symbol = apex_symbol
        self.binance_symbol = binance_symbol
        self.ws_url = ws_url or settings.binance_display_ticker_ws_url
        self.rest_url = rest_url or settings.binance_display_ticker_rest_url
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_message_at: datetime | None = None
        self._reconnect_count = 0
        self._mode = "websocket"

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "apex_symbol": self.apex_symbol,
            "binance_symbol": self.binance_symbol,
            "feed_type": "binance_display_ticker",
            "mode": self._mode,
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done(),
            "last_message_at": self._last_message_at.isoformat() if self._last_message_at else None,
            "reconnect_count": self._reconnect_count,
        }

    async def _publish_price(self, parsed: dict[str, Any], *, source: str) -> None:
        self._last_message_at = datetime.now(timezone.utc)
        await set_display_price(
            self.apex_symbol,
            parsed["price"],
            parsed["timestamp"],
            source=source,
        )
        await broadcaster.broadcast_display_price(
            {
                "symbol": self.apex_symbol,
                "price": parsed["price"],
                "timestamp": parsed["timestamp"],
                "source": source,
            }
        )

    async def _handle_message(self, message: str) -> None:
        try:
            parsed = parse_display_ticker_message(message, binance_symbol=self.binance_symbol)
            if not parsed:
                return
            await self._publish_price(parsed, source=f"binance_{self.binance_symbol.lower()}_ws")
        except Exception as exc:
            logger.error(
                "binance_display_ticker_message_error",
                apex_symbol=self.apex_symbol,
                error=str(exc),
            )

    def _should_fallback_to_rest(self, exc: Exception, ws_attempts: int) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code in (451, 403):
            return True
        message = str(exc).lower()
        if "451" in message or "403" in message:
            return True
        return ws_attempts >= 3

    async def _rest_poll_loop(self) -> None:
        self._mode = "rest"
        source = f"binance_{self.binance_symbol.lower()}_rest"
        logger.warning(
            "binance_display_ticker_rest_fallback",
            apex_symbol=self.apex_symbol,
            url=self.rest_url,
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            while self._running:
                try:
                    response = await client.get(self.rest_url)
                    if response.is_success:
                        parsed = parse_rest_ticker_payload(
                            response.json(),
                            binance_symbol=self.binance_symbol,
                        )
                        if parsed:
                            await self._publish_price(parsed, source=source)
                    else:
                        logger.warning(
                            "binance_display_ticker_rest_error",
                            apex_symbol=self.apex_symbol,
                            status_code=response.status_code,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "binance_display_ticker_rest_error",
                        apex_symbol=self.apex_symbol,
                        error=str(exc),
                    )
                await asyncio.sleep(settings.binance_display_ticker_poll_seconds)

    async def _fetch_and_publish_rest_once(self) -> bool:
        source = f"binance_{self.binance_symbol.lower()}_rest"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.rest_url)
                if not response.is_success:
                    return False
                parsed = parse_rest_ticker_payload(
                    response.json(),
                    binance_symbol=self.binance_symbol,
                )
                if parsed:
                    await self._publish_price(parsed, source=source)
                    return True
        except Exception as exc:
            logger.warning(
                "binance_display_ticker_rest_bootstrap_error",
                apex_symbol=self.apex_symbol,
                error=str(exc),
            )
        return False

    async def _connect_loop(self) -> None:
        await self._fetch_and_publish_rest_once()
        backoff = 1
        ws_attempts = 0
        while self._running:
            try:
                self._mode = "websocket"
                logger.info(
                    "binance_display_ticker_connecting",
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
                    ws_attempts = 0
                    logger.info("binance_display_ticker_connected", apex_symbol=self.apex_symbol)
                    try:
                        first = await asyncio.wait_for(ws.recv(), timeout=12)
                        await self._handle_message(first)
                    except TimeoutError:
                        logger.warning(
                            "binance_display_ticker_no_messages",
                            apex_symbol=self.apex_symbol,
                            url=self.ws_url,
                        )
                        if await self._fetch_and_publish_rest_once():
                            await self._rest_poll_loop()
                            return
                        ws_attempts += 1
                        if self._should_fallback_to_rest(TimeoutError("no ws messages"), ws_attempts):
                            await self._rest_poll_loop()
                            return
                        continue
                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(message)
            except ConnectionClosed as exc:
                logger.warning(
                    "binance_display_ticker_disconnected",
                    apex_symbol=self.apex_symbol,
                    code=exc.code,
                    reason=str(exc.reason),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                ws_attempts += 1
                logger.error(
                    "binance_display_ticker_error",
                    apex_symbol=self.apex_symbol,
                    error=str(exc),
                    attempt=ws_attempts,
                )
                if self._should_fallback_to_rest(exc, ws_attempts):
                    await self._rest_poll_loop()
                    return

            if self._running:
                self._reconnect_count += 1
                logger.info(
                    "binance_display_ticker_reconnecting",
                    apex_symbol=self.apex_symbol,
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
            name=f"display_ticker_{self.apex_symbol}",
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


# Backwards-compatible alias used in tests/imports.
parse_mini_ticker_message = parse_display_ticker_message
