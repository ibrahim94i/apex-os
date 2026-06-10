"""Feed manager — starts, tracks, and restarts per-asset feeds."""

from __future__ import annotations

from typing import Any

from app.config.assets import ACTIVE_SYMBOLS, ASSETS, AssetConfig, get_asset
from app.config import settings
from app.feeds.alphavantage import AlphaVantageFeed
from app.feeds.binance_rest import BinanceRestFeed
from app.feeds.binance_ws import BinanceWebSocketFeed
from app.feeds.frankfurter import FrankfurterFeed
from app.feeds.twelvedata import TwelveDataFeed
from app.logging_config import logger
from app.services.pipeline import process_bar

FeedHandle = BinanceWebSocketFeed | BinanceRestFeed | TwelveDataFeed | AlphaVantageFeed | FrankfurterFeed


async def _handle_feed_bar(raw_bar: dict[str, Any]) -> None:
    symbol = raw_bar.get("symbol", "")
    asset = get_asset(symbol)
    skip_agents = bool(
        raw_bar.get("is_closed", True)
        and asset is not None
        and asset.feed_type == "frankfurter"
    )
    if skip_agents and raw_bar.get("is_closed", True):
        from app.services.h1_bar_gate import should_run_h1_pipeline

        if await should_run_h1_pipeline(symbol, raw_bar["timestamp"]):
            from app.services.agent_analysis_service import run_agent_analysis

            await run_agent_analysis(symbol, force=True)
            return
    await process_bar(raw_bar, skip_agents=skip_agents)


class FeedManager:
    def __init__(self) -> None:
        self._feeds: dict[str, FeedHandle] = {}

    def start_all(self) -> None:
        for symbol in ACTIVE_SYMBOLS:
            self.start_feed(symbol)

    def start_feed(self, symbol: str) -> bool:
        if symbol not in ACTIVE_SYMBOLS:
            return False
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
        for symbol in ACTIVE_SYMBOLS:
            if await self.restart_feed(symbol):
                restarted.append(symbol)
        return restarted

    def get_feed(self, symbol: str) -> FeedHandle | None:
        return self._feeds.get(symbol)

    def is_running(self, symbol: str) -> bool:
        feed = self._feeds.get(symbol)
        return feed.is_running if feed else False

    def get_status(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for symbol, feed in self._feeds.items():
            out[symbol] = feed.status()
        for symbol in ACTIVE_SYMBOLS:
            if symbol not in out:
                asset = get_asset(symbol)
                out[symbol] = {
                    "symbol": symbol,
                    "feed_type": asset.feed_type if asset else None,
                    "running": False,
                    "task_alive": False,
                }
        return out

    def _create_feed(self, asset: AssetConfig) -> FeedHandle | None:
        if asset.feed_type == "binance":
            stagger = ACTIVE_SYMBOLS.index(asset.symbol) * 6 if asset.symbol in ACTIVE_SYMBOLS else 0
            if asset.binance_ws_url:
                return BinanceWebSocketFeed(
                    ws_url=asset.binance_ws_url,
                    on_bar=_handle_feed_bar,
                    apex_symbol=asset.symbol,
                )
            return BinanceRestFeed(
                symbol=asset.symbol,
                apex_symbol=asset.symbol,
                interval=asset.candle_interval,
                poll_interval=asset.poll_interval,
                on_bar=_handle_feed_bar,
                stagger_seconds=stagger,
            )
        if asset.feed_type == "twelvedata" and asset.twelvedata_symbol:
            stagger = ACTIVE_SYMBOLS.index(asset.symbol) * 6 if asset.symbol in ACTIVE_SYMBOLS else 0
            return TwelveDataFeed(
                api_key=settings.twelvedata_api_key,
                symbol=asset.twelvedata_symbol,
                apex_symbol=asset.symbol,
                interval=asset.candle_interval,
                poll_interval=asset.poll_interval,
                on_bar=_handle_feed_bar,
                stagger_seconds=stagger,
            )
        if (
            asset.feed_type == "alphavantage"
            and asset.alphavantage_from_symbol
            and asset.alphavantage_to_symbol
        ):
            return AlphaVantageFeed(
                api_key=settings.alphavantage_api_key,
                from_symbol=asset.alphavantage_from_symbol,
                to_symbol=asset.alphavantage_to_symbol,
                apex_symbol=asset.symbol,
                interval=asset.candle_interval,
                poll_interval=asset.poll_interval,
                on_bar=_handle_feed_bar,
                stagger_seconds=5,
            )
        if (
            asset.feed_type == "frankfurter"
            and asset.frankfurter_from_symbol
            and asset.frankfurter_to_symbol
        ):
            return FrankfurterFeed(
                from_symbol=asset.frankfurter_from_symbol,
                to_symbol=asset.frankfurter_to_symbol,
                apex_symbol=asset.symbol,
                poll_interval=asset.poll_interval,
                on_bar=_handle_feed_bar,
                stagger_seconds=3,
            )
        return None


feed_manager = FeedManager()
