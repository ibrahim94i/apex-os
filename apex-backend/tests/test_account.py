"""Tests for Demo/Real account switching."""

import pytest
from unittest.mock import AsyncMock, patch

from app.config.accounts import get_balance_for_mode
from app.services.account_service import account_service


def test_demo_balance() -> None:
    assert get_balance_for_mode("demo") == 10_000.0


def test_real_balance() -> None:
    assert get_balance_for_mode("real") == 100.0


@pytest.mark.asyncio
async def test_set_and_get_mode() -> None:
    with patch("app.services.account_service.cache_set", new_callable=AsyncMock):
        with patch(
            "app.services.account_service.cache_get",
            new_callable=AsyncMock,
            return_value={"mode": "real"},
        ):
            mode = await account_service.get_mode()
            assert mode == "real"
            status = await account_service.get_status("real")
            assert status["balance"] == 100.0
            assert status["label_ar"] == "حقيقي"
