"""Tests for tiered selectivity and strong-consensus technical bypass."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.engines.indicator_engine import OHLCVBar
from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema, RegimeType, SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict
from app.services.signal_filters import (
    apply_high_selectivity_filters,
    check_confluence,
    should_bypass_rsi_atr_filters,
    should_bypass_technical_filters,
)


def _indicators(**kwargs) -> IndicatorSnapshotSchema:
    base = dict(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        rsi=70.0,
        macd=1.0,
        macd_signal=0.5,
        ema_50=2100.0,
        ema_200=2000.0,
        atr=1.0,
        atr_avg_20=4.0,
    )
    base.update(kwargs)
    return IndicatorSnapshotSchema(**base)


def _regime(**kwargs) -> RegimeSnapshotSchema:
    base = dict(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        regime=RegimeType.TRENDING_UP,
        confidence=0.8,
        adx_value=30.0,
        volatility_pct=1.0,
        trend_strength=0.5,
    )
    base.update(kwargs)
    return RegimeSnapshotSchema(**base)


def _consensus(final_confidence: float = 0.72) -> AgentConsensus:
    now = datetime.now(timezone.utc)
    return AgentConsensus(
        symbol="XAUUSD",
        timestamp=now,
        final_direction=SignalDirection.LONG,
        final_confidence=final_confidence,
        verdicts=[
            AgentVerdict(
                agent_id=AgentRole.MARKET_ANALYST,
                agent_name_ar="محلل السوق",
                direction=SignalDirection.LONG,
                confidence=0.60,
                reasoning=["test"],
                weight=0.4,
            ),
            AgentVerdict(
                agent_id=AgentRole.RISK,
                agent_name_ar="المخاطر",
                direction=SignalDirection.LONG,
                confidence=0.60,
                reasoning=["test"],
                weight=0.35,
            ),
        ],
        vote_scores={"market_analyst": 0.4, "risk": 0.35},
    )


def test_bypass_when_confidence_above_70_and_direction_clear() -> None:
    assert should_bypass_technical_filters(SignalDirection.LONG, 0.71) is True
    assert should_bypass_technical_filters(SignalDirection.SHORT, 0.80) is True
    assert should_bypass_rsi_atr_filters(_consensus(0.72)) is True


def test_no_bypass_when_confidence_at_or_below_70() -> None:
    assert should_bypass_technical_filters(SignalDirection.LONG, 0.70) is False
    assert should_bypass_technical_filters(SignalDirection.LONG, 0.69) is False
    assert should_bypass_technical_filters(SignalDirection.NEUTRAL, 0.90) is False


def test_confluence_skip_rsi_allows_extreme_rsi() -> None:
    ok, reason = check_confluence(
        SignalDirection.LONG,
        _indicators(rsi=80.0),
        skip_rsi=True,
    )
    assert ok is True
    assert reason is None


def test_confluence_enforces_rsi_by_default() -> None:
    ok, reason = check_confluence(SignalDirection.LONG, _indicators(rsi=80.0))
    assert ok is False
    assert reason == "rsi_out_of_range"


@pytest.mark.asyncio
async def test_strong_consensus_bypasses_rsi_and_atr_filters() -> None:
    bars = [OHLCVBar(timestamp=datetime.now(timezone.utc), open=1, high=1, low=1, close=1, volume=1)] * 25

    with patch(
        "app.services.signal_filters.is_gold_trading_session",
        return_value=True,
    ), patch(
        "app.services.signal_filters.check_news_block",
        new=AsyncMock(return_value=False),
    ):
        allowed, reason = await apply_high_selectivity_filters(
            "EURUSD",
            SignalDirection.LONG,
            0.72,
            _indicators(rsi=80.0, atr=1.0, atr_avg_20=4.0),
            _regime(adx_value=10.0),
            bars,
            _consensus(),
        )

    assert allowed is True
    assert reason is None


@pytest.mark.asyncio
async def test_marginal_confidence_applies_rsi_filter() -> None:
    bars = [OHLCVBar(timestamp=datetime.now(timezone.utc), open=1, high=1, low=1, close=1, volume=1)] * 25

    with patch(
        "app.services.signal_filters.is_gold_trading_session",
        return_value=True,
    ), patch(
        "app.services.signal_filters.check_news_block",
        new=AsyncMock(return_value=False),
    ):
        allowed, reason = await apply_high_selectivity_filters(
            "EURUSD",
            SignalDirection.LONG,
            0.70,
            _indicators(rsi=80.0),
            _regime(),
            bars,
            _consensus(0.70),
        )

    assert allowed is False
    assert reason == "rsi_out_of_range"


@pytest.mark.asyncio
async def test_confidence_below_70_rejected() -> None:
    with patch(
        "app.services.signal_filters.is_gold_trading_session",
        return_value=True,
    ):
        allowed, reason = await apply_high_selectivity_filters(
            "EURUSD",
            SignalDirection.LONG,
            0.69,
            _indicators(),
            _regime(),
            [],
            _consensus(0.69),
        )

    assert allowed is False
    assert reason == "confidence_below_threshold"
