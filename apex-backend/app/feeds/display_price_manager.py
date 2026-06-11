"""Start/stop dashboard-only display price feeds (isolated from analysis pipeline)."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.config.assets import ACTIVE_SYMBOLS
from app.feeds.binance_display_ticker import BinanceDisplayTickerFeed
from app.logging_config import logger

FeedHandle = BinanceDisplayTickerFeed


class DisplayPriceFeedManager:
    def __init__(self) -> None:
        self._feeds: dict[str, FeedHandle] = {}

    def start_all(self) -> None:
        if not settings.binance_display_ticker_enabled:
            return
        if "XAUUSD" in ACTIVE_SYMBOLS and "XAUUSD" not in self._feeds:
            feed = BinanceDisplayTickerFeed(
                apex_symbol="XAUUSD",
                binance_symbol="XAUUSDT",
            )
            feed.start()
            self._feeds["XAUUSD"] = feed
            logger.info(
                "display_price_feed_started",
                apex_symbol="XAUUSD",
                binance_symbol="XAUUSDT",
            )

    async def stop_all(self) -> None:
        for symbol in list(self._feeds):
            await self.stop_feed(symbol)

    async def stop_feed(self, symbol: str) -> None:
        feed = self._feeds.pop(symbol, None)
        if feed:
            await feed.stop()

    def get_status(self) -> dict[str, dict[str, Any]]:
        return {symbol: feed.status() for symbol, feed in self._feeds.items()}


display_price_manager = DisplayPriceFeedManager()
