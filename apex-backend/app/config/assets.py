"""Multi-asset configuration — single source of truth for all tradable symbols."""

from dataclasses import dataclass
from typing import Literal

SIGNAL_TIMEFRAME = "1h"
POLL_INTERVAL_SECONDS = 180  # XAUUSD TwelveData — 480 calls/day (86400/180)
EURUSD_POLL_INTERVAL_SECONDS = 300  # EURUSD TwelveData — 288 calls/day (86400/300)
# TwelveData credits: 1 credit per data point returned (not per HTTP call).
# Live polls (outputsize=1): XAUUSD 480/day + EURUSD 288/day = 768 credits/day.
# Bootstrap is DB-first; API bootstrap only when DB is below threshold.

MarketSchedule = Literal["24_7", "xauusd", "forex_24_5"]


@dataclass(frozen=True)
class AssetConfig:
    symbol: str
    display_name_ar: str
    feed_type: Literal["binance", "twelvedata", "alphavantage", "frankfurter"]
    market_schedule: MarketSchedule = "24_7"
    binance_ws_url: str | None = None
    twelvedata_symbol: str | None = None
    alphavantage_from_symbol: str | None = None
    alphavantage_to_symbol: str | None = None
    frankfurter_from_symbol: str | None = None
    frankfurter_to_symbol: str | None = None
    candle_interval: str = SIGNAL_TIMEFRAME
    poll_interval: int = POLL_INTERVAL_SECONDS
    finnhub_symbol: str | None = None
    min_price_move: float | None = None
    default_spread: float | None = None
    price_decimals: int = 2
    volume_reliable: bool = True


# BTCUSDT: Binance REST (free, no TwelveData credits). FX/metals: TwelveData + Frankfurter.
ASSETS: dict[str, AssetConfig] = {
    "BTCUSDT": AssetConfig(
        symbol="BTCUSDT",
        display_name_ar="بيتكوين",
        feed_type="binance",
        market_schedule="24_7",
        candle_interval="1h",
        poll_interval=POLL_INTERVAL_SECONDS,
        finnhub_symbol="OANDA:BTC_USD",
        min_price_move=50.0,
        default_spread=15.0,
        price_decimals=2,
    ),
    "XAUUSD": AssetConfig(
        symbol="XAUUSD",
        display_name_ar="الذهب",
        feed_type="twelvedata",
        market_schedule="xauusd",
        twelvedata_symbol="XAU/USD",
        finnhub_symbol="OANDA:XAU_USD",
        candle_interval="1h",
        poll_interval=POLL_INTERVAL_SECONDS,
        min_price_move=0.50,
        default_spread=0.30,
        volume_reliable=False,
    ),
    "EURUSD": AssetConfig(
        symbol="EURUSD",
        display_name_ar="يورو/دولار",
        feed_type="twelvedata",
        market_schedule="forex_24_5",
        twelvedata_symbol="EUR/USD",
        finnhub_symbol="OANDA:EUR_USD",
        candle_interval="1h",
        poll_interval=EURUSD_POLL_INTERVAL_SECONDS,
        min_price_move=0.00050,
        default_spread=0.00015,
        price_decimals=5,
    ),
    "USDJPY": AssetConfig(
        symbol="USDJPY",
        display_name_ar="دولار/ين",
        feed_type="frankfurter",
        market_schedule="forex_24_5",
        frankfurter_from_symbol="USD",
        frankfurter_to_symbol="JPY",
        finnhub_symbol="OANDA:USD_JPY",
        candle_interval="1h",
        poll_interval=POLL_INTERVAL_SECONDS,
        min_price_move=0.02,
        default_spread=0.01,
        price_decimals=3,
    ),
    "GBPUSD": AssetConfig(
        symbol="GBPUSD",
        display_name_ar="جنيه/دولار",
        feed_type="frankfurter",
        market_schedule="forex_24_5",
        frankfurter_from_symbol="GBP",
        frankfurter_to_symbol="USD",
        finnhub_symbol="OANDA:GBP_USD",
        candle_interval="1h",
        poll_interval=POLL_INTERVAL_SECONDS,
        min_price_move=0.00050,
        default_spread=0.00015,
        price_decimals=5,
    ),
}

# Active trading universe (EURUSD/GBPUSD paused — XAUUSD + USDJPY only)
ACTIVE_SYMBOLS: list[str] = ["XAUUSD", "USDJPY"]


def get_asset(symbol: str) -> AssetConfig | None:
    return ASSETS.get(symbol)
