"""Tests for account balance configuration."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.account_service import AccountService


@pytest.mark.asyncio
async def test_demo_balance_fixed_at_10000() -> None:
    svc = AccountService()
    with patch.object(svc, "get_mode", new_callable=AsyncMock, return_value="demo"):
        balance = await svc.get_balance()
    assert balance == 10000.0


@pytest.mark.asyncio
async def test_real_balance_default_100() -> None:
    svc = AccountService()
    with patch.object(svc, "get_mode", new_callable=AsyncMock, return_value="real"):
        with patch.object(svc, "get_real_balance_override", new_callable=AsyncMock, return_value=None):
            balance = await svc.get_balance()
    assert balance == 100.0


@pytest.mark.asyncio
async def test_real_balance_custom_override() -> None:
    svc = AccountService()
    with patch("app.services.account_service.cache_set", new_callable=AsyncMock):
        with patch.object(svc, "get_mode", new_callable=AsyncMock, return_value="real"):
            with patch.object(
                svc, "get_real_balance_override", new_callable=AsyncMock, return_value=500.0
            ):
                balance = await svc.get_balance()
    assert balance == 500.0


@pytest.mark.asyncio
async def test_set_real_balance() -> None:
    svc = AccountService()
    with patch("app.services.account_service.cache_set", new_callable=AsyncMock) as mock_set:
        with patch.object(svc, "get_mode", new_callable=AsyncMock, return_value="real"):
            with patch.object(
                svc, "get_real_balance_override", new_callable=AsyncMock, return_value=250.0
            ):
                status = await svc.set_real_balance(250.0)
    assert status["balance"] == 250.0
    assert status["balance_editable"] is True
    mock_set.assert_called()
