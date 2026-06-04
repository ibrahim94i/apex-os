"""Finnhub market news for the news agent (forex + macro headlines)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.logging_config import logger
from app.schemas.agent import NewsHeadline

FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"

# Keywords to rank headlines per tradable symbol (headline + summary, lowercased).
_SYMBOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "XAUUSD": (
        "gold",
        "xau",
        "precious",
        "bullion",
        "safe haven",
        "fed",
        "federal reserve",
        "inflation",
        "cpi",
        "treasury",
        "dollar",
        "dxy",
        "rate",
        "powell",
        "geopolit",
        "war",
        "middle east",
        "yield",
    ),
    "EURUSD": (
        "eur",
        "euro",
        "ecb",
        "europe",
        "eurozone",
        "german",
        "france",
        "italy",
        "fed",
        "dollar",
        "inflation",
        "cpi",
        "rate",
        "forex",
        "currency",
        "trade",
        "pmi",
    ),
    "USDJPY": (
        "yen",
        "jpy",
        "japan",
        "boj",
        "bank of japan",
        "tokyo",
        "usd",
        "dollar",
        "fed",
        "rate",
        "inflation",
        "cpi",
        "forex",
        "carry",
        "intervention",
    ),
    "BTCUSDT": (
        "bitcoin",
        "btc",
        "crypto",
        "fed",
        "dollar",
        "regulation",
        "etf",
    ),
}

_CATEGORY_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SECONDS = 300.0


def _is_configured() -> bool:
    key = settings.finnhub_api_key
    return bool(key and key != "your_key_here")


def _keyword_score(symbol: str, article: dict[str, Any]) -> int:
    keywords = _SYMBOL_KEYWORDS.get(symbol, ())
    if not keywords:
        return 0
    text = f"{article.get('headline', '')} {article.get('summary', '')}".lower()
    return sum(1 for kw in keywords if kw in text)


def _parse_published(article: dict[str, Any]) -> datetime | None:
    ts = article.get("datetime")
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return None


def _to_headline(article: dict[str, Any]) -> NewsHeadline:
    return NewsHeadline(
        headline=str(article.get("headline") or "").strip(),
        summary=str(article.get("summary") or "").strip()[:500],
        source=str(article.get("source") or "").strip(),
        url=str(article.get("url") or "").strip(),
        category=str(article.get("category") or "").strip(),
        published_at=_parse_published(article),
    )


async def _fetch_category(category: str) -> list[dict[str, Any]]:
    now = time.monotonic()
    cached = _CATEGORY_CACHE.get(category)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    if not _is_configured():
        return []

    params = {"category": category, "token": settings.finnhub_api_key}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(FINNHUB_NEWS_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("finnhub_news_fetch_failed", category=category, error=str(exc))
        return []

    if not isinstance(data, list):
        return []

    _CATEGORY_CACHE[category] = (now, data)
    return data


def _dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for article in articles:
        aid = article.get("id")
        if isinstance(aid, int) and aid in seen:
            continue
        if isinstance(aid, int):
            seen.add(aid)
        out.append(article)
    return out


async def fetch_news_for_symbol(symbol: str, *, limit: int | None = None) -> list[NewsHeadline]:
    """Return up to `limit` Finnhub headlines most relevant to the symbol."""
    max_items = limit or settings.finnhub_news_limit
    if not _is_configured():
        return []

    categories = (
        ("forex", "general")
        if symbol in ("XAUUSD", "EURUSD", "USDJPY")
        else ("forex", "crypto")
    )
    merged: list[dict[str, Any]] = []
    for cat in categories:
        merged.extend(await _fetch_category(cat))

    merged = _dedupe_articles(merged)
    scored = [(a, _keyword_score(symbol, a)) for a in merged]
    scored.sort(
        key=lambda pair: (
            pair[1],
            pair[0].get("datetime") or 0,
        ),
        reverse=True,
    )

    # Prefer symbol-relevant items; if none match keywords, use latest forex headlines.
    relevant = [a for a, score in scored if score > 0]
    pool = relevant if relevant else [a for a, _ in scored]

    headlines: list[NewsHeadline] = []
    for article in pool:
        if not article.get("headline"):
            continue
        headlines.append(_to_headline(article))
        if len(headlines) >= max_items:
            break

    logger.info(
        "finnhub_news_fetched",
        symbol=symbol,
        count=len(headlines),
        relevant=bool(relevant),
    )
    return headlines
