"""Alpha Vantage NEWS_SENTIMENT — real-time news with built-in sentiment."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.feeds.alphavantage_limiter import throttled_get
from app.logging_config import logger
from app.schemas.agent import NewsHeadline

AV_NEWS_URL = "https://www.alphavantage.co/query"

_SYMBOL_TOPICS: dict[str, str] = {
    "XAUUSD": "financial_markets,economy_monetary,economy_macro",
    "EURUSD": "forex,financial_markets,economy_monetary",
    "USDJPY": "forex,financial_markets,economy_monetary",
    "GBPUSD": "forex,financial_markets,economy_monetary",
    "BTCUSDT": "financial_markets,blockchain",
}

_SENTIMENT_MAP = {
    "bullish": ("إيجابي", 0.6),
    "somewhat-bullish": ("إيجابي جزئياً", 0.35),
    "neutral": ("محايد", 0.0),
    "somewhat-bearish": ("سلبي جزئياً", -0.35),
    "bearish": ("سلبي", -0.6),
}

_CACHE: dict[str, tuple[float, list[NewsHeadline]]] = {}
_CACHE_TTL = 300.0


def _is_configured() -> bool:
    key = settings.alphavantage_api_key
    return bool(key and key not in ("", "your_key_here"))


def _parse_time_published(raw: str | None) -> datetime | None:
    if not raw or len(raw) < 15:
        return None
    try:
        dt = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _normalize_sentiment(label: str | None, score: float | None) -> tuple[float | None, str]:
    if label:
        key = label.strip().lower().replace("_", "-")
        if key in _SENTIMENT_MAP:
            ar_label, default_score = _SENTIMENT_MAP[key]
            return (score if score is not None else default_score, ar_label)
    if score is not None:
        if score > 0.15:
            return score, "إيجابي"
        if score < -0.15:
            return score, "سلبي"
        return score, "محايد"
    return None, ""


def _article_to_headline(article: dict[str, Any]) -> NewsHeadline | None:
    title = str(article.get("title") or "").strip()
    if not title:
        return None
    raw_score = article.get("overall_sentiment_score")
    score = float(raw_score) if isinstance(raw_score, (int, float, str)) and raw_score != "" else None
    if isinstance(score, str):
        try:
            score = float(score)
        except ValueError:
            score = None
    label = str(article.get("overall_sentiment_label") or "")
    norm_score, ar_label = _normalize_sentiment(label, score)
    return NewsHeadline(
        headline=title[:300],
        summary=str(article.get("summary") or "").strip()[:500],
        source=str(article.get("source") or "Alpha Vantage").strip(),
        provider="alphavantage",
        url=str(article.get("url") or "").strip(),
        category=str(article.get("category_within_source") or "news").strip(),
        published_at=_parse_time_published(str(article.get("time_published") or "")),
        sentiment_score=norm_score,
        sentiment_label=ar_label or label,
    )


async def fetch_alphavantage_news(symbol: str, *, limit: int = 15) -> list[NewsHeadline]:
    if not _is_configured() or not settings.alphavantage_news_enabled:
        return []

    cache_key = f"{symbol}:{limit}"
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    topics = _SYMBOL_TOPICS.get(symbol, "financial_markets,forex")
    params = {
        "function": "NEWS_SENTIMENT",
        "topics": topics,
        "limit": str(min(limit, 50)),
        "apikey": settings.alphavantage_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await throttled_get(client, AV_NEWS_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("alphavantage_news_fetch_failed", symbol=symbol, error=str(exc))
        return []

    if not isinstance(data, dict):
        return []
    if data.get("Note") or data.get("Information"):
        logger.warning("alphavantage_news_rate_limited", symbol=symbol)
        return []

    feed = data.get("feed")
    if not isinstance(feed, list):
        return []

    headlines: list[NewsHeadline] = []
    for article in feed:
        if not isinstance(article, dict):
            continue
        headline = _article_to_headline(article)
        if headline:
            headlines.append(headline)
        if len(headlines) >= limit:
            break

    _CACHE[cache_key] = (now, headlines)
    logger.info("alphavantage_news_fetched", symbol=symbol, count=len(headlines))
    return headlines
