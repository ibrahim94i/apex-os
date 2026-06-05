"""GBPUSD and poll interval configuration."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS
from app.feeds.manager import feed_manager
from app.services.market_hours import SCHEDULE_LABELS
from app.services.telegram_notifier import ASSET_AR

POLL_INTERVAL_SECONDS = 300


def test_active_symbols_four_assets() -> None:
    assert ACTIVE_SYMBOLS == ["XAUUSD", "EURUSD", "USDJPY", "GBPUSD"]
    assert "BTCUSDT" not in ACTIVE_SYMBOLS


def test_fx_active_assets_poll_five_minutes() -> None:
    for symbol in ("EURUSD", "USDJPY", "GBPUSD"):
        assert ASSETS[symbol].poll_interval == POLL_INTERVAL_SECONDS


def test_gbpusd_twelvedata_config() -> None:
    asset = ASSETS["GBPUSD"]
    assert asset.feed_type == "twelvedata"
    assert asset.twelvedata_symbol == "GBP/USD"
    assert asset.market_schedule == "forex_24_5"
    assert asset.price_decimals == 5


def test_telegram_label_gbpusd() -> None:
    assert ASSET_AR["GBPUSD"] == "جنيه/دولار"


def test_schedule_label_gbpusd() -> None:
    assert "GBPUSD" in SCHEDULE_LABELS


def test_feed_manager_creates_gbpusd_feed() -> None:
    gbp = ASSETS["GBPUSD"]
    assert feed_manager._create_feed(gbp) is not None
