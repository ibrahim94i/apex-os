"""USDJPY asset configuration (XAGUSD removed — TwelveData free tier)."""

from app.config.assets import ACTIVE_SYMBOLS, ASSETS
from app.feeds.manager import feed_manager
from app.services.market_hours import SCHEDULE_LABELS
from app.services.telegram_notifier import ASSET_AR


def test_active_symbols_three_assets() -> None:
    assert ACTIVE_SYMBOLS == ["XAUUSD", "EURUSD", "USDJPY"]
    assert "BTCUSDT" not in ACTIVE_SYMBOLS
    assert "XAGUSD" not in ACTIVE_SYMBOLS


def test_usdjpy_twelvedata_config() -> None:
    asset = ASSETS["USDJPY"]
    assert asset.feed_type == "twelvedata"
    assert asset.twelvedata_symbol == "USD/JPY"
    assert asset.market_schedule == "forex_24_5"
    assert asset.price_decimals == 3


def test_telegram_label_usdjpy() -> None:
    assert ASSET_AR["USDJPY"] == "دولار/ين"


def test_schedule_label_usdjpy() -> None:
    assert "USDJPY" in SCHEDULE_LABELS


def test_feed_manager_creates_usdjpy_feed() -> None:
    jpy = ASSETS["USDJPY"]
    assert feed_manager._create_feed(jpy) is not None
