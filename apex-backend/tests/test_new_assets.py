"""GBPUSD and poll interval configuration."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS, POLL_INTERVAL_SECONDS
from app.feeds.manager import feed_manager
from app.services.market_hours import SCHEDULE_LABELS
from app.services.telegram_notifier import ASSET_AR


def test_active_symbols_four_assets() -> None:
    assert ACTIVE_SYMBOLS == ["XAUUSD", "EURUSD", "USDJPY", "GBPUSD"]
    assert "BTCUSDT" not in ACTIVE_SYMBOLS


def test_fx_frankfurter_pairs_poll_three_minutes() -> None:
    for symbol in ("USDJPY", "GBPUSD"):
        assert ASSETS[symbol].poll_interval == POLL_INTERVAL_SECONDS


def test_eurusd_twelvedata_poll_five_minutes() -> None:
    assert ASSETS["EURUSD"].poll_interval == 300
    assert ASSETS["EURUSD"].feed_type == "twelvedata"


def test_gbpusd_frankfurter_config() -> None:
    asset = ASSETS["GBPUSD"]
    assert asset.feed_type == "frankfurter"
    assert asset.frankfurter_from_symbol == "GBP"
    assert asset.frankfurter_to_symbol == "USD"
    assert asset.market_schedule == "forex_24_5"
    assert asset.price_decimals == 5


def test_telegram_label_gbpusd() -> None:
    assert ASSET_AR["GBPUSD"] == "جنيه/دولار"


def test_schedule_label_gbpusd() -> None:
    assert "GBPUSD" in SCHEDULE_LABELS


def test_feed_manager_creates_btcusdt_binance_feed() -> None:
    btc = ASSETS["BTCUSDT"]
    feed = feed_manager._create_feed(btc)
    assert feed is not None
    from app.feeds.binance_rest import BinanceRestFeed

    assert isinstance(feed, BinanceRestFeed)
    assert feed.poll_interval == 180


def test_feed_manager_creates_eurusd_twelvedata_feed() -> None:
    eur = ASSETS["EURUSD"]
    feed = feed_manager._create_feed(eur)
    assert feed is not None
    from app.feeds.twelvedata import TwelveDataFeed

    assert isinstance(feed, TwelveDataFeed)
    assert feed.poll_interval == 300


def test_feed_manager_creates_gbpusd_feed() -> None:
    gbp = ASSETS["GBPUSD"]
    feed = feed_manager._create_feed(gbp)
    assert feed is not None
    from app.feeds.frankfurter import FrankfurterFeed

    assert isinstance(feed, FrankfurterFeed)
