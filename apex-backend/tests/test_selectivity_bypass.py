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
    passes_selectivity_confidence_floor,
    should_bypass_all_selectivity_filters,
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


def _consensus(
    final_confidence: float = 0.72,
    final_direction: SignalDirection = SignalDirection.LONG,
) -> AgentConsensus:
    now = datetime.now(timezone.utc)
    return AgentConsensus(
        symbol="XAUUSD",
        timestamp=now,
        final_direction=final_direction,
        final_confidence=final_confidence,
        verdicts=[
            AgentVerdict(
                agent_id=AgentRole.MARKET_ANALYST,
                agent_name_ar="محلل السوق",
                direction=final_direction,
                confidence=0.80,
                reasoning=["test"],
                weight=0.4,
            ),
            AgentVerdict(
                agent_id=AgentRole.RISK,
                agent_name_ar="المخاطr",
                direction=final_direction,
                confidence=0.75,
                reasoning=["test"],
                weight=0.35,
            ),
        ],
        vote_scores={"market_analyst": 0.4, "risk": 0.35},
    )


def test_bypass_only_when_collective_at_least_75_and_trending() -> None:
    regime = _regime(regime=RegimeType.TRENDING_DOWN)
    assert should_bypass_all_selectivity_filters(_consensus(0.76, SignalDirection.SHORT), regime) is True
    assert should_bypass_technical_filters(
        SignalDirection.SHORT, 0.50, _consensus(0.76, SignalDirection.SHORT), regime
    ) is True
    assert should_bypass_rsi_atr_filters(
        SignalDirection.LONG, 0.50, _consensus(0.75), _regime()
    ) is True


def test_no_bypass_in_70_to_75_band_or_without_clear_trend() -> None:
    trending = _regime(regime=RegimeType.TRENDING_UP)
    assert should_bypass_all_selectivity_filters(_consensus(0.73), trending) is False
    assert should_bypass_technical_filters(SignalDirection.LONG, 0.50, _consensus(0.73), trending) is False
    assert should_bypass_rsi_atr_filters(SignalDirection.LONG, 0.50, _consensus(0.70), trending) is False
    assert should_bypass_all_selectivity_filters(_consensus(0.80), _regime(regime=RegimeType.RANGING)) is False
    assert should_bypass_technical_filters(SignalDirection.LONG, 0.80, _consensus(0.69), trending) is False
    neutral = _consensus(0.90, SignalDirection.NEUTRAL)
    assert should_bypass_rsi_atr_filters(SignalDirection.NEUTRAL, 0.90, neutral, trending) is False


def test_floor_passes_when_consensus_meets_threshold_after_degradation() -> None:
    consensus = _consensus(0.73)
    assert passes_selectivity_confidence_floor(0.584, consensus) is True
    assert passes_selectivity_confidence_floor(0.69, _consensus(0.69)) is False


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
async def test_strong_trend_consensus_bypasses_all_selectivity_filters() -> None:
    bars = [OHLCVBar(timestamp=datetime.now(timezone.utc), open=1, high=1, low=1, close=1, volume=1)] * 25
    regime = _regime(regime=RegimeType.TRENDING_DOWN, adx_value=10.0, volatility_pct=0.1)

    with patch(
        "app.services.signal_filters.is_gold_trading_session",
        return_value=True,
    ), patch(
        "app.services.signal_filters.check_news_block",
        new=AsyncMock(return_value=True),
    ):
        allowed, reason = await apply_high_selectivity_filters(
            "XAUUSD",
            SignalDirection.SHORT,
            0.58,
            _indicators(
                rsi=80.0,
                macd=1.0,
                macd_signal=0.5,
                atr=0.2,
                atr_avg_20=2.0,
            ),
            regime,
            bars,
            _consensus(0.76, SignalDirection.SHORT),
        )

    assert allowed is True
    assert reason is None


@pytest.mark.asyncio
async def test_mid_band_70_to_75_applies_all_filters() -> None:
    bars = [OHLCVBar(timestamp=datetime.now(timezone.utc), open=1, high=1, low=1, close=1, volume=1)] * 25
    consensus = _consensus(0.73, SignalDirection.SHORT)

    with patch(
        "app.services.signal_filters.is_gold_trading_session",
        return_value=True,
    ), patch(
        "app.services.signal_filters.check_news_block",
        new=AsyncMock(return_value=False),
    ):
        allowed, reason = await apply_high_selectivity_filters(
            "XAUUSD",
            SignalDirection.SHORT,
            0.584,
            _indicators(
                rsi=50.0,
                macd=-1.0,
                macd_signal=-1.5,
                ema_50=2200.0,
                ema_200=2100.0,
                atr=2.0,
                atr_avg_20=2.0,
            ),
            _regime(regime=RegimeType.TRENDING_DOWN, adx_value=55.0),
            bars,
            consensus,
        )

    assert allowed is False
    assert reason == "ema_confluence_short"


@pytest.mark.asyncio
async def test_mid_band_applies_rsi_filter() -> None:
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
            _consensus(0.73),
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
