"""Verification tests for XAUUSD news relevance filtering."""

from datetime import datetime, timezone

from app.schemas.agent import NewsHeadline
from app.services.news_symbol_filter import filter_headlines_for_symbol, headline_matches_symbol


def _headline(title: str, summary: str = "") -> NewsHeadline:
    return NewsHeadline(
        headline=title,
        summary=summary,
        provider="test",
        published_at=datetime.now(timezone.utc),
    )


SAMPLE_HEADLINES = [
    _headline("Gold prices rise on safe-haven demand", "XAUUSD hits session high"),
    _headline("Fed signals pause on rate hikes", "Dollar weakens after FOMC"),
    _headline("Eurozone PMI beats expectations", "EUR strength vs dollar"),
    _headline("Apple stock hits record high", "Tech rally continues"),
    _headline("Oil prices surge on Middle East tensions", "Energy markets volatile"),
    _headline("Bitcoin ETF inflows accelerate", "Crypto markets rally"),
]


def test_xauusd_keeps_gold_and_macro_drivers() -> None:
    filtered = filter_headlines_for_symbol("XAUUSD", SAMPLE_HEADLINES)
    titles = {item.headline for item in filtered}
    assert "Gold prices rise on safe-haven demand" in titles
    assert "Fed signals pause on rate hikes" in titles
    assert "Oil prices surge on Middle East tensions" in titles


def test_xauusd_drops_unrelated_headlines() -> None:
    filtered = filter_headlines_for_symbol("XAUUSD", SAMPLE_HEADLINES)
    titles = {item.headline for item in filtered}
    assert "Eurozone PMI beats expectations" not in titles
    assert "Apple stock hits record high" not in titles
    assert "Bitcoin ETF inflows accelerate" not in titles


def test_verification_report() -> None:
    """Printable verification matrix for XAUUSD headline filtering."""
    rows = []
    for item in SAMPLE_HEADLINES:
        rows.append(
            {
                "headline": item.headline,
                "matches_xauusd": headline_matches_symbol("XAUUSD", item),
            }
        )

    kept = sum(1 for row in rows if row["matches_xauusd"])
    dropped = len(rows) - kept

    assert kept == 3
    assert dropped == 3

    # Exposed for manual inspection when running pytest -s
    report_lines = [
        "XAUUSD news filter verification",
        f"kept={kept} dropped={dropped}",
    ]
    for row in rows:
        status = "KEEP" if row["matches_xauusd"] else "DROP"
        report_lines.append(f"[{status}] {row['headline']}")
    print("\n".join(report_lines))
