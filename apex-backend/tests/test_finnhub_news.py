"""Tests for Finnhub news integration."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.news.prompt import build_user_prompt, format_news_block
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType
from app.schemas.agent import MarketSnapshot, NewsHeadline
from app.schemas.snapshots import KillSwitchStatusSchema
from app.services.finnhub_news import fetch_finnhub_headlines


def _snapshot(symbol: str, headlines: list[NewsHeadline]) -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    return MarketSnapshot(
        symbol=symbol,
        timestamp=now,
        price=2650.0 if symbol == "XAUUSD" else 1.085,
        indicators=IndicatorSnapshotSchema(symbol=symbol, timestamp=now, rsi=50.0),
        regime=RegimeSnapshotSchema(
            symbol=symbol,
            timestamp=now,
            regime=RegimeType.TRENDING_UP,
            confidence=0.7,
        ),
        kill_switch=KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE),
        account_balance=10000.0,
        max_risk_pct=1.0,
        max_drawdown_pct=5.0,
        news_headlines=headlines,
    )


@pytest.mark.asyncio
async def test_fetch_finnhub_headlines_filters_gold() -> None:
    articles = [
        {
            "id": 1,
            "datetime": 1700000000,
            "headline": "Gold prices rise on Fed rate outlook",
            "summary": "XAU safe haven demand increases",
            "source": "Reuters",
            "url": "https://example.com/1",
            "category": "forex",
        },
        {
            "id": 2,
            "datetime": 1699999990,
            "headline": "Eurozone PMI beats expectations",
            "summary": "EUR strength vs dollar",
            "source": "Bloomberg",
            "url": "https://example.com/2",
            "category": "forex",
        },
    ]

    with patch("app.services.finnhub_news._is_configured", return_value=True):
        with patch(
            "app.services.finnhub_news._fetch_category",
            new_callable=AsyncMock,
            return_value=articles,
        ):
            headlines = await fetch_finnhub_headlines("XAUUSD", limit=5)

    assert len(headlines) >= 1
    assert headlines[0].provider == "finnhub"
    assert "gold" in headlines[0].headline.lower() or "xau" in headlines[0].summary.lower()


@pytest.mark.asyncio
async def test_fetch_finnhub_headlines_filters_euro() -> None:
    articles = [
        {
            "id": 1,
            "datetime": 1700000000,
            "headline": "Gold prices rise on Fed rate outlook",
            "summary": "XAU safe haven demand increases",
            "source": "Reuters",
            "url": "https://example.com/1",
            "category": "forex",
        },
        {
            "id": 2,
            "datetime": 1699999990,
            "headline": "Eurozone PMI beats expectations",
            "summary": "EUR strength vs dollar",
            "source": "Bloomberg",
            "url": "https://example.com/2",
            "category": "forex",
        },
    ]

    with patch("app.services.finnhub_news._is_configured", return_value=True):
        with patch(
            "app.services.finnhub_news._fetch_category",
            new_callable=AsyncMock,
            return_value=articles,
        ):
            headlines = await fetch_finnhub_headlines("EURUSD", limit=5)

    assert len(headlines) >= 1
    assert "euro" in headlines[0].headline.lower() or "eur" in headlines[0].summary.lower()


def test_news_prompt_includes_multi_source_headlines() -> None:
    headlines = [
        NewsHeadline(
            headline="ECB holds rates steady",
            summary="Euro traders watch inflation",
            source="CNBC",
            provider="cnbc",
            sentiment_label="محايد",
            published_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
        )
    ]
    snap = _snapshot("EURUSD", headlines)
    block = format_news_block(snap)
    prompt = build_user_prompt(snap)

    assert "Alpha Vantage" in block
    assert "ECB holds rates steady" in prompt
    assert "sentiment" in block
    assert "EURUSD" in prompt
