"""Free RSS news feeds — Reuters, Bloomberg, CNBC, MarketWatch, Investing.com, FXStreet."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.logging_config import logger
from app.schemas.agent import NewsHeadline

RSS_FEEDS: tuple[tuple[str, str, int], ...] = (
    ("reuters", "https://feeds.reuters.com/reuters/businessNews", 10),
    ("bloomberg", "https://feeds.bloomberg.com/markets/news.rss", 10),
    (
        "cnbc",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        10,
    ),
    ("marketwatch", "https://feeds.marketwatch.com/marketwatch/topstories/", 10),
    ("investing", "https://www.investing.com/rss/news.rss", 10),
    ("fxstreet", "https://www.fxstreet.com/rss/news", 10),
)

_USER_AGENT = "APEX-OS/1.0 (+https://github.com/ibrahim94i/apex-os)"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_CACHE: dict[str, tuple[float, list[NewsHeadline]]] = {}
_CACHE_TTL = 300.0


def _parse_published(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw[:19], fmt[:19])
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_rss_xml(content: str, provider: str, limit: int) -> list[NewsHeadline]:
    headlines: list[NewsHeadline] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return headlines

    items = root.findall(".//item")
    if not items:
        items = root.findall(".//atom:entry", _ATOM_NS)

    for item in items[:limit]:
        if item.tag.endswith("entry"):
            title = (item.findtext("atom:title", default="", namespaces=_ATOM_NS) or "").strip()
            link_el = item.find("atom:link", _ATOM_NS)
            url = link_el.get("href", "") if link_el is not None else ""
            summary = (
                item.findtext("atom:summary", default="", namespaces=_ATOM_NS)
                or item.findtext("atom:content", default="", namespaces=_ATOM_NS)
                or ""
            ).strip()
            published = (
                item.findtext("atom:updated", default="", namespaces=_ATOM_NS)
                or item.findtext("atom:published", default="", namespaces=_ATOM_NS)
            )
        else:
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            summary = (item.findtext("description") or item.findtext("content") or "").strip()
            published = item.findtext("pubDate") or item.findtext("published")

        if not title:
            continue

        headlines.append(
            NewsHeadline(
                headline=_strip_html(title)[:300],
                summary=_strip_html(summary)[:500],
                source=provider.title(),
                provider=provider,
                url=url,
                category="rss",
                published_at=_parse_published(published),
            )
        )
    return headlines


async def _fetch_feed(provider: str, url: str, limit: int) -> list[NewsHeadline]:
    cache_key = f"{provider}:{limit}"
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            headlines = _parse_rss_xml(response.text, provider, limit)
    except Exception as exc:
        logger.warning("rss_feed_fetch_failed", provider=provider, error=str(exc))
        return []

    _CACHE[cache_key] = (now, headlines)
    return headlines


async def fetch_all_rss_feeds() -> list[NewsHeadline]:
    """Fetch configured RSS feeds in parallel."""
    import asyncio

    tasks = [_fetch_feed(provider, url, limit) for provider, url, limit in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged: list[NewsHeadline] = []
    for result in results:
        if isinstance(result, list):
            merged.extend(result)
    return merged
