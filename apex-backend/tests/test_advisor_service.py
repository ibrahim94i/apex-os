"""Tests for Smart Advisor service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.advisor_service import (
    _build_user_prompt,
    _ensure_intraday_disclaimer,
    _format_apex_context,
    advisor_chat,
    build_asset_advisor_context,
)
from app.services.advisor_prompt import INTRADAY_DISCLAIMER
from app.schemas.advisor import AdvisorAssetContext
from app.utils.llm_client import LLMResponse


@pytest.mark.asyncio
async def test_build_asset_advisor_context() -> None:
    with patch(
        "app.services.advisor_service.get_latest_price",
        new=AsyncMock(return_value={"price": 4400.0, "timestamp": "2026-06-01T12:00:00+00:00"}),
    ):
        with patch(
            "app.services.advisor_service.get_latest_regime",
            new=AsyncMock(
                return_value={
                    "symbol": "XAUUSD",
                    "regime": "TRENDING_UP",
                    "confidence": 0.9,
                    "adx_value": 30.0,
                }
            ),
        ):
            with patch(
                "app.services.advisor_service._load_indicators",
                new=AsyncMock(return_value={"rsi": 55.0, "adx": 30.0, "macd": 1.2}),
            ):
                with patch(
                    "app.services.advisor_service.get_agent_consensus",
                    new=AsyncMock(return_value=None),
                ):
                    with patch(
                        "app.services.advisor_service.get_latest_signal",
                        new=AsyncMock(return_value=None),
                    ):
                        with patch(
                            "app.services.advisor_service.fetch_news_for_symbol",
                            new=AsyncMock(return_value=[]),
                        ):
                            ctx = await build_asset_advisor_context("XAUUSD")
    assert ctx.symbol == "XAUUSD"
    assert ctx.price == 4400.0
    assert ctx.rsi == 55.0


def test_format_apex_context_includes_symbol() -> None:
    ctx = AdvisorAssetContext(
        symbol="EURUSD",
        display_name_ar="يورو/دولار",
        price=1.08,
        rsi=50.0,
        data_complete=True,
    )
    text = _format_apex_context([ctx])
    assert "EURUSD" in text
    assert "RSI" in text


def test_ensure_intraday_disclaimer_appended() -> None:
    reply = _ensure_intraday_disclaimer("توصية: شراء")
    assert INTRADAY_DISCLAIMER in reply


def test_ensure_intraday_disclaimer_not_duplicated() -> None:
    text = f"توصية\n\n{INTRADAY_DISCLAIMER}"
    assert _ensure_intraday_disclaimer(text) == text


@pytest.mark.asyncio
async def test_build_user_prompt_includes_intraday_horizon() -> None:
    ctx = AdvisorAssetContext(
        symbol="XAUUSD",
        display_name_ar="الذهب",
        price=4400.0,
        data_complete=True,
    )
    with patch(
        "app.services.advisor_service._build_intraday_block",
        new=AsyncMock(return_value="نطاق الدخول المسموح (±0.5%)"),
    ):
        prompt = await _build_user_prompt("ما توصيتك للذهب؟", [ctx], "XAUUSD")
    assert "15–60 دقيقة" in prompt
    assert "±0.5%" in prompt
    assert "ما توصيتك للذهب؟" in prompt


@pytest.mark.asyncio
async def test_advisor_chat_calls_llm_with_web_search() -> None:
    mock_response = LLMResponse(
        content="توصية: انتظار — الثقة 65%",
        model="gpt-4o-mini",
        latency_ms=1200.0,
        provider="openai_web",
    )
    mock_client = MagicMock()
    mock_client.is_configured = True
    mock_client.advisor_chat_with_web_search = AsyncMock(return_value=mock_response)
    with patch(
        "app.services.advisor_service.build_all_advisor_context",
        new=AsyncMock(
            return_value=[
                AdvisorAssetContext(symbol="XAUUSD", display_name_ar="الذهب", data_complete=True)
            ]
        ),
    ):
        with patch("app.services.advisor_service.llm_client", mock_client):
            with patch(
                "app.services.advisor_service._build_user_prompt",
                new=AsyncMock(return_value="prompt"),
            ):
                result = await advisor_chat("ما رأيك في الذهب؟", symbol="XAUUSD")
    assert "توصية" in result.reply
    assert INTRADAY_DISCLAIMER in result.reply
    assert result.web_search_used is True
    mock_client.advisor_chat_with_web_search.assert_awaited_once()
