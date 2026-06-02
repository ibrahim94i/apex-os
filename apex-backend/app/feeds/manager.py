"""Feed manager — starts, tracks, and restarts per-asset feeds."""

from __future__ import annotations

from typing import Any

from app.config.assets import ASSETS, AssetConfig, get_asset
from app.config import settings
from app.feeds.binance_ws import BinanceWebSocketFeed
from app.feeds.twelvedata import TwelveDataFeed
from app.logging_config import logger
from app.services.pipeline import process_bar


class FeedManager:
    def __init__(self) -> None:
        self._feeds: dict[str, BinanceWebSocketFeed | TwelveDataFeed] = {}

    def start_all(self) -> None:
        for symbol in ASSETS:
            self.start_feed(symbol)

    def start_feed(self, symbol: str) -> bool:
        if symbol in self._feeds and self._feeds[symbol].is_running:
            return False

        asset = get_asset(symbol)
        if asset is None:
            return False

        feed = self._create_feed(asset)
        if feed is None:
            return False

        feed.start()
        self._feeds[symbol] = feed
        logger.info("feed_started", symbol=symbol, feed_type=asset.feed_type)
        return True

    async def stop_feed(self, symbol: str) -> None:
        feed = self._feeds.pop(symbol, None)
        if feed:
            await feed.stop()

    async def stop_all(self) -> None:
        for symbol in list(self._feeds):
            await self.stop_feed(symbol)

    async def restart_feed(self, symbol: str) -> bool:
        await self.stop_feed(symbol)
        return self.start_feed(symbol)

    async def restart_all(self) -> list[str]:
        restarted: list[str] = []
        for symbol in ASSETS:
            if await self.restart_feed(symbol):
                restarted.append(symbol)
        return restarted

    def get_feed(self, symbol: str) -> BinanceWebSocketFeed | TwelveDataFeed | None:
        return self._feeds.get(symbol)

    def is_running(self, symbol: str) -> bool:
        feed = self._feeds.get(symbol)
        return feed.is_running if feed else False

    def get_status(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for symbol, feed in self._feeds.items():
            out[symbol] = feed.status()
        for symbol in ASSETS:
            if symbol not in out:
                asset = get_asset(symbol)
                out[symbol] = {
                    "symbol": symbol,
                    "feed_type": asset.feed_type if asset else None,
                    "running": False,
                    "task_alive": False,
                }
        return out

    def _create_feed(
        self, asset: AssetConfig
    ) -> BinanceWebSocketFeed | TwelveDataFeed | None:
        if asset.feed_type == "binance" and asset.binance_ws_url:
            return BinanceWebSocketFeed(
                ws_url=asset.binance_ws_url,
                on_bar=process_bar,
                apex_symbol=asset.symbol,
            )
        if asset.feed_type == "twelvedata" and asset.twelvedata_symbol:
            stagger = 120 if asset.symbol == "EURUSD" else 0
            return TwelveDataFeed(
                api_key=settings.twelvedata_api_key,
                symbol=asset.twelvedata_symbol,
                apex_symbol=asset.symbol,
                interval=asset.candle_interval,
                poll_interval=asset.poll_interval,
                on_bar=process_bar,
                stagger_seconds=stagger,
            )
        return None


feed_manager = FeedManager()
