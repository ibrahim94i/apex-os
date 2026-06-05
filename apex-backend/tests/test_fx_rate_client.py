"""Tests for FX rate provider chain."""

from unittest.mock import AsyncMock, patch

import pytest

from app.feeds.fx_rate_client import (
    build_hourly_bar,
    fetch_latest_rate,
    fetch_latest_rate_with_source,
)


@pytest.mark.asyncio
async def test_fetch_latest_rate_uses_exchangerate_api_first() -> None:
    with patch(
        "app.feeds.fx_rate_client._fetch_exchangerate_api",
        new=AsyncMock(return_value=1.1626),
    ) as mock_er:
        rate, source = await fetch_latest_rate_with_source("EUR", "USD")
    assert rate == 1.1626
    assert source == "exchangerate_api"
    mock_er.assert_awaited_once_with("EUR", "USD")


@pytest.mark.asyncio
async def test_fetch_latest_rate_falls_back_to_fixer() -> None:
    with patch(
        "app.feeds.fx_rate_client._fetch_exchangerate_api",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.feeds.fx_rate_client._fetch_fixer",
            new=AsyncMock(return_value=159.96),
        ) as mock_fixer:
            rate, source = await fetch_latest_rate_with_source("USD", "JPY")
    assert rate == 159.96
    assert source == "fixer"
    mock_fixer.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_latest_rate_returns_none_when_all_fail() -> None:
    with patch(
        "app.feeds.fx_rate_client._fetch_exchangerate_api",
        new=AsyncMock(return_value=None),
    ):
        with patch(
            "app.feeds.fx_rate_client._fetch_fixer",
            new=AsyncMock(return_value=None),
        ):
            with patch(
                "app.feeds.fx_rate_client._fetch_currencyapi",
                new=AsyncMock(return_value=None),
            ):
                rate, source = await fetch_latest_rate_with_source("GBP", "USD")
    assert rate is None
    assert source is None


@pytest.mark.asyncio
async def test_fetch_latest_rate_wrapper() -> None:
    with patch(
        "app.feeds.fx_rate_client.fetch_latest_rate_with_source",
        new=AsyncMock(return_value=(1.3449, "exchangerate_api")),
    ):
        rate = await fetch_latest_rate("GBP", "USD")
    assert rate == 1.3449


def test_build_hourly_bar_uses_source() -> None:
    bar = build_hourly_bar(apex_symbol="EURUSD", price=1.08, source="exchangerate_api")
    assert bar["source"] == "exchangerate_api"
    assert bar["close"] == 1.08
