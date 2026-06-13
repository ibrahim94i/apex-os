"""Symbol-specific headline relevance filtering for the news agent."""

from __future__ import annotations

from app.schemas.agent import NewsHeadline

# Headline + summary must contain at least one keyword (case-insensitive substring).
SYMBOL_NEWS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "XAUUSD": (
        "gold",
        "xau",
        "xauusd",
        "bullion",
        "precious metal",
        "precious metals",
        "safe haven",
        "safe-haven",
        "fed",
        "federal reserve",
        "fomc",
        "powell",
        "inflation",
        "cpi",
        "ppi",
        "treasury",
        "yield",
        "real yield",
        "dollar",
        "dxy",
        "usd",
        "rate cut",
        "rate hike",
        "interest rate",
        "geopolit",
        "middle east",
        "war",
        "conflict",
        "central bank",
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
    "GBPUSD": (
        "gbp",
        "pound",
        "sterling",
        "uk",
        "britain",
        "boe",
        "bank of england",
        "london",
        "brexit",
        "fed",
        "dollar",
        "inflation",
        "cpi",
        "rate",
        "forex",
        "currency",
        "pmi",
    ),
    "BTCUSDT": (
        "bitcoin",
        "btc",
        "crypto",
        "cryptocurrency",
        "blockchain",
        "fed",
        "dollar",
        "regulation",
        "etf",
    ),
}


def headline_text(headline: NewsHeadline) -> str:
    return f"{headline.headline} {headline.summary}".lower()


def _has_gold_primary(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "gold",
            "xau",
            "bullion",
            "precious metal",
            "precious metals",
            "safe haven",
            "safe-haven",
        )
    )


def _is_other_asset_headline(text: str) -> bool:
    markers = (
        " eur",
        "eur/",
        " euro",
        "ecb",
        "eurozone",
        " yen",
        " jpy",
        "boj",
        " gbp",
        "pound sterling",
        "bitcoin",
        " btc",
        "crypto",
        "ethereum",
        "apple",
        "microsoft",
        "nasdaq",
        " s&p",
        "tesla",
    )
    return any(marker in text for marker in markers)


def headline_matches_symbol(symbol: str, headline: NewsHeadline) -> bool:
    keywords = SYMBOL_NEWS_KEYWORDS.get(symbol.upper())
    if not keywords:
        return True
    text = headline_text(headline)

    if symbol.upper() == "XAUUSD":
        if _is_other_asset_headline(text) and not _has_gold_primary(text):
            return False

    return any(keyword in text for keyword in keywords)


def filter_headlines_for_symbol(
    symbol: str,
    headlines: list[NewsHeadline],
) -> list[NewsHeadline]:
    """Keep only headlines relevant to the trading symbol."""
    return [headline for headline in headlines if headline_matches_symbol(symbol, headline)]
