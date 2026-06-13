"""Filter headlines by age and build news-agent freshness metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import settings
from app.schemas import SignalDirection
from app.schemas.agent import NewsAgentLLMOutput, NewsHeadline

NEWS_STALE_WARNING_AR = "⚠️ لا أخبار حديثة"


@dataclass(frozen=True)
class NewsFreshnessInfo:
    fresh_headlines: list[NewsHeadline]
    recent_count: int
    last_fresh_at: datetime | None
    total_fetched: int
    ignored_stale_count: int
    has_recent_news: bool


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def filter_fresh_headlines(
    headlines: list[NewsHeadline],
    *,
    ref: datetime | None = None,
    max_age_seconds: int | None = None,
) -> NewsFreshnessInfo:
    """Keep headlines published within max_age_seconds; ignore older or undated items."""
    now = _coerce_utc(ref or datetime.now(timezone.utc))
    max_age = max_age_seconds if max_age_seconds is not None else settings.news_max_age_seconds

    fresh: list[NewsHeadline] = []
    last_at: datetime | None = None
    ignored = 0

    for headline in headlines:
        if headline.published_at is None:
            ignored += 1
            continue
        published = _coerce_utc(headline.published_at)
        age_seconds = (now - published).total_seconds()
        if age_seconds > max_age:
            ignored += 1
            continue
        fresh.append(headline)
        if last_at is None or published > last_at:
            last_at = published

    return NewsFreshnessInfo(
        fresh_headlines=fresh,
        recent_count=len(fresh),
        last_fresh_at=last_at,
        total_fetched=len(headlines),
        ignored_stale_count=ignored,
        has_recent_news=len(fresh) > 0,
    )


def stale_news_neutral_output(info: NewsFreshnessInfo) -> NewsAgentLLMOutput:
    """Force neutral verdict when no headline is fresh enough."""
    reasoning: list[str] = [NEWS_STALE_WARNING_AR]
    if info.total_fetched == 0:
        reasoning.append("لا توجد عناوين من المصادر")
    elif info.ignored_stale_count > 0:
        reasoning.append(f"تم تجاهل {info.ignored_stale_count} خبر أقدم من ساعة")

    return NewsAgentLLMOutput(
        direction=SignalDirection.NEUTRAL,
        confidence=0.55,
        reasoning=reasoning,
        asset_impacts={"XAUUSD": "neutral"},
        overall_risk_level="medium",
        recommendation_ar="انتظار — لا أخبار حديثة",
    )
