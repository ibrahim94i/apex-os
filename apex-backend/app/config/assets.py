"""Multi-asset configuration — single source of truth for all tradable symbols."""

from dataclasses import dataclass
from typing import Literal

SIGNAL_TIMEFRAME = "1h"

MarketSchedule = Literal["24_7", "xauusd", "forex_24_5"]


@dataclass(frozen=True)
class AssetConfig:
    symbol: str
    display_name_ar: str
    feed_type: Literal["binance", "twelvedata", "alphavantage"]
    market_schedule: MarketSchedule = "24_7"
    binance_ws_url: str | None = None
    twelvedata_symbol: str | None = None
    alphavantage_from_symbol: str | None = None
    alphavantage_to_symbol: str | None = None
    candle_interval: str = SIGNAL_TIMEFRAME
    poll_interval: int = 300
    min_price_move: float | None = None
    default_spread: float | None = None
    price_decimals: int = 2


ASSETS: dict[str, AssetConfig] = {
    "BTCUSDT": AssetConfig(
        symbol="BTCUSDT",
        display_name_ar="بيتكوين",
        feed_type="twelvedata",
        market_schedule="24_7",
        twelvedata_symbol="BTC/USD",
        candle_interval="1h",
        poll_interval=300,
    ),
    "XAUUSD": AssetConfig(
        symbol="XAUUSD",
        display_name_ar="الذهب",
        feed_type="twelvedata",
        market_schedule="xauusd",
        twelvedata_symbol="XAU/USD",
        candle_interval="1h",
        poll_interval=300,
        min_price_move=0.50,
        default_spread=0.30,
    ),
    "EURUSD": AssetConfig(
        symbol="EURUSD",
        display_name_ar="يورو/دولار",
        feed_type="alphavantage",
        market_schedule="forex_24_5",
        alphavantage_from_symbol="EUR",
        alphavantage_to_symbol="USD",
        candle_interval="1h",
        poll_interval=3600,
        min_price_move=0.00050,
        default_spread=0.00015,
        price_decimals=5,
    ),
}

ACTIVE_SYMBOLS: list[str] = list(ASSETS.keys())


def get_asset(symbol: str) -> AssetConfig | None:
    return ASSETS.get(symbol)
