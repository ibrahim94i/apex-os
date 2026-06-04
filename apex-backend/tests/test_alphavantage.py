"""Tests for Alpha Vantage FX feed parsing (legacy fallback)."""

from app.feeds.alphavantage_client import parse_fx_intraday_payload


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
        },
    }
    bars = parse_fx_intraday_payload(data, apex_symbol="EURUSD", interval="1h")
    assert len(bars) == 1
    assert bars[0]["close"] == 1.0895
