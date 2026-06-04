"""Tests for demo balance always fixed at 10k."""

from app.config.accounts import get_demo_balance, get_balance_for_mode


def test_demo_balance_always_10000() -> None:
    assert get_demo_balance() == 10_000.0
    assert get_balance_for_mode("demo") == 10_000.0
