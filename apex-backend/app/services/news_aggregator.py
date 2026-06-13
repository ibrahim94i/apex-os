"""Multi-source news aggregation — Finnhub, Alpha Vantage, RSS feeds."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from app.config import settings
from app.logging_config import logger
from app.schemas.agent import NewsHeadline
from app.services.finnhub_news import fetch_finnhub_headlines
from app.services.news_sources.alphavantage_news import fetch_alphavantage_news
from app.services.news_sources.rss_feeds import fetch_all_rss_feeds
from app.services.news_symbol_filter import filter_headlines_for_symbol


def _normalize_headline_key(headline: str) -> str:
    text = headline.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text)


def dedupe_headlines(headlines: list[NewsHeadline]) -> list[NewsHeadline]:
    seen: set[str] = set()
    out: list[NewsHeadline] = []
    for item in headlines:
        key = _normalize_headline_key(item.headline)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def sort_headlines_newest_first(headlines: list[NewsHeadline]) -> list[NewsHeadline]:
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def sort_key(item: NewsHeadline) -> datetime:
        return item.published_at or epoch

    return sorted(headlines, key=sort_key, reverse=True)


async def fetch_news_for_symbol(symbol: str, *, limit: int | None = None) -> list[NewsHeadline]:
    """Fetch, dedupe, and sort headlines from all configured sources."""
    max_items = limit or settings.news_aggregate_limit

    results = await asyncio.gather(
        fetch_finnhub_headlines(symbol),
        fetch_alphavantage_news(symbol, limit=settings.alphavantage_news_limit),
        fetch_all_rss_feeds(),
        return_exceptions=True,
    )

    merged: list[NewsHeadline] = []
    source_counts: dict[str, int] = {}
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("news_source_failed", error=str(result))
            continue
        for headline in result:
            merged.append(headline)
            provider = headline.provider or "unknown"
            source_counts[provider] = source_counts.get(provider, 0) + 1

    filtered = filter_headlines_for_symbol(symbol, merged)
    deduped = dedupe_headlines(filtered)
    sorted_headlines = sort_headlines_newest_first(deduped)[:max_items]

    logger.info(
        "news_aggregated",
        symbol=symbol,
        total=len(merged),
        filtered=len(filtered),
        deduped=len(deduped),
        returned=len(sorted_headlines),
        sources=source_counts,
    )
    return sorted_headlines
