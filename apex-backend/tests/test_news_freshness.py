"""Tests for news headline freshness filtering."""

from datetime import datetime, timedelta, timezone

import pytest

from app.agents.news.agent import NewsAgent
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.agent import MarketSnapshot, NewsHeadline
from app.schemas.snapshots import KillSwitchStatusSchema
from app.services.news_freshness import (
    NEWS_STALE_WARNING_AR,
    filter_fresh_headlines,
    stale_news_neutral_output,
)


def _headline(minutes_ago: int, *, title: str = "Gold rises") -> NewsHeadline:
    now = datetime.now(timezone.utc)
    return NewsHeadline(
        headline=title,
        provider="finnhub",
        published_at=now - timedelta(minutes=minutes_ago),
        sentiment_score=0.2,
    )


def test_filter_keeps_headlines_within_one_hour() -> None:
    now = datetime.now(timezone.utc)
    info = filter_fresh_headlines(
        [_headline(30), _headline(90, title="Old")],
        ref=now,
    )
    assert info.recent_count == 1
    assert info.ignored_stale_count == 1
    assert info.has_recent_news is True
    assert info.last_fresh_at is not None


def test_filter_ignores_headlines_without_timestamp() -> None:
    now = datetime.now(timezone.utc)
    info = filter_fresh_headlines(
        [NewsHeadline(headline="No time", provider="rss")],
        ref=now,
    )
    assert info.recent_count == 0
    assert info.has_recent_news is False


def test_stale_news_forces_neutral_output() -> None:
    now = datetime.now(timezone.utc)
    info = filter_fresh_headlines([_headline(120)], ref=now)
    output = stale_news_neutral_output(info)
    assert output.direction == SignalDirection.NEUTRAL
    assert NEWS_STALE_WARNING_AR in output.reasoning[0]


@pytest.mark.asyncio
async def test_news_agent_neutral_when_all_headlines_old() -> None:
    from unittest.mock import MagicMock

    now = datetime.now(timezone.utc)
    snapshot = MarketSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        price=2650.0,
        indicators=IndicatorSnapshotSchema(symbol="XAUUSD", timestamp=now, rsi=50.0),
        regime=RegimeSnapshotSchema(
            symbol="XAUUSD",
            timestamp=now,
            regime=RegimeType.TRENDING_UP,
            confidence=0.7,
        ),
        kill_switch=KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE),
        account_balance=10000.0,
        max_risk_pct=1.0,
        max_drawdown_pct=5.0,
        news_headlines=[_headline(180)],
    )
    mock_client = MagicMock()
    mock_client.is_configured = False
    verdict = await NewsAgent(client=mock_client).analyze(snapshot)
    assert verdict.direction == SignalDirection.NEUTRAL
    assert verdict.news_recent_count == 0
    assert verdict.news_stale_warning_ar == NEWS_STALE_WARNING_AR
