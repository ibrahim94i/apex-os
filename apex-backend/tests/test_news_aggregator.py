"""Tests for multi-source news aggregation."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.agent import NewsHeadline
from app.services.news_aggregator import (
    dedupe_headlines,
    fetch_news_for_symbol,
    sort_headlines_newest_first,
)
from app.services.news_sources.rss_feeds import _parse_rss_xml


def test_dedupe_headlines() -> None:
    items = [
        NewsHeadline(headline="Gold rises on Fed outlook", provider="reuters"),
        NewsHeadline(headline="Gold rises on Fed outlook!", provider="bloomberg"),
        NewsHeadline(headline="Euro PMI beats", provider="cnbc"),
    ]
    result = dedupe_headlines(items)
    assert len(result) == 2


def test_sort_headlines_newest_first() -> None:
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 6, 4, tzinfo=timezone.utc)
    items = [
        NewsHeadline(headline="old", published_at=old),
        NewsHeadline(headline="new", published_at=new),
    ]
    sorted_items = sort_headlines_newest_first(items)
    assert sorted_items[0].headline == "new"


def test_parse_rss_xml_extracts_items() -> None:
    xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Test headline</title>
        <link>https://example.com</link>
        <description>Summary text</description>
        <pubDate>Wed, 04 Jun 2026 12:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    headlines = _parse_rss_xml(xml, "reuters", 10)
    assert len(headlines) == 1
    assert headlines[0].headline == "Test headline"
    assert headlines[0].provider == "reuters"


@pytest.mark.asyncio
async def test_fetch_news_for_symbol_merges_sources() -> None:
    finnhub = [
        NewsHeadline(
            headline="Gold hits record",
            provider="finnhub",
            published_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
        )
    ]
    av = [
        NewsHeadline(
            headline="Fed signals pause",
            provider="alphavantage",
            sentiment_label="إيجابي",
            sentiment_score=0.4,
            published_at=datetime(2026, 6, 4, 11, 0, tzinfo=timezone.utc),
        )
    ]
    rss = [
        NewsHeadline(
            headline="Dollar weakens on Fed outlook",
            provider="fxstreet",
            published_at=datetime(2026, 6, 4, 9, 0, tzinfo=timezone.utc),
        ),
        NewsHeadline(
            headline="Apple hits new record high",
            provider="cnbc",
            published_at=datetime(2026, 6, 4, 8, 0, tzinfo=timezone.utc),
        ),
    ]

    with patch(
        "app.services.news_aggregator.fetch_finnhub_headlines",
        new=AsyncMock(return_value=finnhub),
    ), patch(
        "app.services.news_aggregator.fetch_alphavantage_news",
        new=AsyncMock(return_value=av),
    ), patch(
        "app.services.news_aggregator.fetch_all_rss_feeds",
        new=AsyncMock(return_value=rss),
    ):
        headlines = await fetch_news_for_symbol("XAUUSD", limit=10)

    assert len(headlines) == 3
    assert headlines[0].headline == "Fed signals pause"
    assert headlines[0].sentiment_label == "إيجابي"
    assert all("Apple" not in h.headline for h in headlines)


@pytest.mark.asyncio
async def test_fetch_news_dedupes_across_sources() -> None:
    duplicate = NewsHeadline(
        headline="Eurozone inflation cools as ECB watches EUR",
        summary="EURUSD traders focus on euro area CPI",
        provider="reuters",
        published_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )
    with patch(
        "app.services.news_aggregator.fetch_finnhub_headlines",
        new=AsyncMock(return_value=[duplicate]),
    ), patch(
        "app.services.news_aggregator.fetch_alphavantage_news",
        new=AsyncMock(return_value=[duplicate.model_copy(update={"provider": "alphavantage"})]),
    ), patch(
        "app.services.news_aggregator.fetch_all_rss_feeds",
        new=AsyncMock(return_value=[]),
    ):
        headlines = await fetch_news_for_symbol("EURUSD")

    assert len(headlines) == 1
