"""Tests for asset polling intervals."""

from app.config.assets import ASSETS


def test_xauusd_poll_interval_three_minutes() -> None:
    assert ASSETS["XAUUSD"].poll_interval == 180


def test_eurusd_poll_interval_three_minutes() -> None:
    assert ASSETS["EURUSD"].poll_interval == 180
