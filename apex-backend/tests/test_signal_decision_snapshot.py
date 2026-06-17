"""Tests for immutable signal decision snapshots (Phase 3)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engines.indicator_engine import OHLCVBar
from app.schemas import RegimeType, SignalDirection, TradingSignalSchema
from app.schemas.agent import AgentConsensus, AgentVerdict, AgentRole
from app.schemas.snapshots import IndicatorSnapshotSchema, RegimeSnapshotSchema
from app.services.signal_decision_snapshot_service import (
    build_frozen_signal_decision_snapshot,
    compute_dataset_hash,
    persist_signal_decision_snapshot,
)


def _bars() -> list[OHLCVBar]:
    return [
        OHLCVBar(
            timestamp=datetime(2026, 6, 17, 18, 0, tzinfo=timezone.utc),
            open=4300.0,
            high=4310.0,
            low=4295.0,
            close=4305.0,
            volume=10.0,
        )
    ]


def _indicators(close_time: datetime) -> IndicatorSnapshotSchema:
    return IndicatorSnapshotSchema(
        symbol="XAUUSD",
        timestamp=close_time,
        rsi=55.0,
        adx=25.0,
        atr=5.0,
    )


def _regime(close_time: datetime) -> RegimeSnapshotSchema:
    return RegimeSnapshotSchema(
        symbol="XAUUSD",
        timestamp=close_time,
        regime=RegimeType.TRENDING_UP,
        confidence=0.8,
        adx_value=25.0,
        volatility_pct=0.3,
        trend_strength=0.2,
    )


def _signal(close_time: datetime) -> TradingSignalSchema:
    return TradingSignalSchema(
        symbol="XAUUSD",
        timestamp=close_time,
        direction=SignalDirection.LONG,
        confidence=0.75,
        entry_price=4305.0,
        stop_loss=4290.0,
        take_profit=4325.0,
        regime=RegimeType.TRENDING_UP,
    )


def _consensus(close_time: datetime) -> AgentConsensus:
    return AgentConsensus(
        symbol="XAUUSD",
        timestamp=close_time,
        final_direction=SignalDirection.LONG,
        final_confidence=0.75,
        verdicts=[
            AgentVerdict(
                agent_id=AgentRole.MARKET_ANALYST,
                agent_name_ar="محلل",
                direction=SignalDirection.LONG,
                confidence=0.75,
                reasoning=["test"],
                weight=1.0,
            )
        ],
        vote_scores={"LONG": 1.0},
        signal_decision="emitted",
    )


def test_compute_dataset_hash_is_stable_for_same_bars() -> None:
    bars = _bars()
    assert compute_dataset_hash(bars) == compute_dataset_hash(bars)
    assert len(compute_dataset_hash(bars)) == 64


def test_compute_dataset_hash_changes_when_bars_differ() -> None:
    bars_a = _bars()
    bars_b = [
        OHLCVBar(
            timestamp=datetime(2026, 6, 17, 18, 0, tzinfo=timezone.utc),
            open=4300.0,
            high=4310.0,
            low=4295.0,
            close=4306.0,
            volume=10.0,
        )
    ]
    assert compute_dataset_hash(bars_a) != compute_dataset_hash(bars_b)


def test_build_frozen_signal_decision_snapshot_complete_status() -> None:
    close_time = datetime(2026, 6, 17, 19, 0, tzinfo=timezone.utc)
    bars = _bars()
    frozen = build_frozen_signal_decision_snapshot(
        symbol="XAUUSD",
        candle_close_time=close_time,
        decision_bars=bars,
        indicators=_indicators(close_time),
        regime=_regime(close_time),
        signal=_signal(close_time),
        snr=None,
        snr_state="NORMAL",
        agent_consensus=_consensus(close_time),
        market_snapshot=None,
    )
    assert frozen.candle_close_time == close_time
    assert frozen.data_source == "metatrader"
    assert frozen.bar_count == 1
    assert frozen.dataset_hash == compute_dataset_hash(bars)
    assert frozen.snapshot_status == "complete"
    assert frozen.trigger_bar.close == 4305.0
    assert frozen.signal.timestamp == close_time
    assert frozen.indicators is not None
    assert frozen.indicators.timestamp == close_time
    assert frozen.agent_consensus is not None
    assert frozen.agent_consensus.signal_decision == "emitted"


def test_build_frozen_signal_decision_snapshot_partial_without_consensus() -> None:
    close_time = datetime(2026, 6, 17, 19, 0, tzinfo=timezone.utc)
    frozen = build_frozen_signal_decision_snapshot(
        symbol="XAUUSD",
        candle_close_time=close_time,
        decision_bars=_bars(),
        indicators=_indicators(close_time),
        regime=_regime(close_time),
        signal=_signal(close_time),
        snr=None,
        snr_state="NORMAL",
        agent_consensus=None,
        market_snapshot=None,
    )
    assert frozen.agent_consensus is None
    assert frozen.snapshot_status == "partial"
    assert frozen.dataset_hash


@pytest.mark.asyncio
async def test_persist_signal_decision_snapshot_is_insert_only() -> None:
    close_time = datetime(2026, 6, 17, 19, 0, tzinfo=timezone.utc)
    frozen = build_frozen_signal_decision_snapshot(
        symbol="XAUUSD",
        candle_close_time=close_time,
        decision_bars=_bars(),
        indicators=_indicators(close_time),
        regime=_regime(close_time),
        signal=_signal(close_time),
        snr=None,
        snr_state="NORMAL",
        agent_consensus=_consensus(close_time),
        market_snapshot=None,
    )
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    row = await persist_signal_decision_snapshot(
        session,
        trading_signal_id=42,
        snapshot=frozen,
    )
    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert row.trading_signal_id == 42
    assert row.symbol == "XAUUSD"
    assert row.payload["signal"]["direction"] == "LONG"
    assert row.payload["snapshot_status"] == "complete"
    assert row.payload["dataset_hash"] == frozen.dataset_hash
