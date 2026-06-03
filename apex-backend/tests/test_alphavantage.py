"""Tests for Alpha Vantage FX feed parsing and config."""

from app.config.assets import ASSETS
from app.feeds.alphavantage_client import parse_fx_intraday_payload


def test_eurusd_uses_alphavantage_feed() -> None:
    asset = ASSETS["EURUSD"]
    assert asset.feed_type == "alphavantage"
    assert asset.alphavantage_from_symbol == "EUR"
    assert asset.alphavantage_to_symbol == "USD"
    assert asset.poll_interval == 3600
    assert asset.twelvedata_symbol is None


def test_xauusd_still_uses_twelvedata() -> None:
    assert ASSETS["XAUUSD"].feed_type == "twelvedata"
    assert ASSETS["BTCUSDT"].feed_type == "twelvedata"


def test_parse_fx_intraday_payload() -> None:
    data = {
        "Meta Data": {},
        "Time Series FX (60min)": {
            "2024-01-15 18:00:00": {
                "1. open": "1.0890",
                "2. high": "1.0900",
                "3. low": "1.0880",
                "4. close": "1.0895",
            },
            "2024-01-15 19:00:00": {
                "1. open": "1.0895",
                "2. high": "1.0910",
                "3. low": "1.0890",
                "4. close": "1.0905",
            },
        },
    }
    bars = parse_fx_intraday_payload(data, apex_symbol="EURUSD", interval="1h")
    assert len(bars) == 2
    assert bars[0]["symbol"] == "EURUSD"
    assert bars[-1]["close"] == 1.0905
    assert bars[-1]["source"] == "alphavantage"
