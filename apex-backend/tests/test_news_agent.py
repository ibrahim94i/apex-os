"""Tests for enhanced news agent."""

from datetime import datetime, timezone

from app.agents.news.agent import WEIGHT, _rule_based
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType
from app.schemas.agent import MarketSnapshot, NewsHeadline
from app.schemas.snapshots import KillSwitchStatusSchema


def _snapshot(headlines: list[NewsHeadline]) -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    return MarketSnapshot(
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
        news_headlines=headlines,
    )


def test_news_agent_weight_is_25_percent() -> None:
    assert WEIGHT == 0.25


def test_rule_based_includes_asset_impacts() -> None:
    headlines = [
        NewsHeadline(
            headline="Gold demand rises",
            provider="alphavantage",
            sentiment_score=0.5,
            sentiment_label="إيجابي",
        )
    ]
    output = _rule_based(_snapshot(headlines))
    assert "XAUUSD" in output.asset_impacts
    assert output.overall_risk_level in ("low", "medium", "high", "critical")
    assert output.recommendation_ar
