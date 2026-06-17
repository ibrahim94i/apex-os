"""Persist immutable decision snapshots when signals are emitted."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.indicator_engine import OHLCVBar
from app.logging_config import logger
from app.models import SignalDecisionSnapshot
from app.schemas import TradingSignalSchema
from app.schemas.agent import AgentConsensus, MarketSnapshot
from app.schemas.signal_decision_snapshot import FrozenBarSchema, SignalDecisionSnapshotSchema
from app.schemas.snr import SNRSnapshotSchema
from app.schemas.snapshots import IndicatorSnapshotSchema, RegimeSnapshotSchema
from app.services.market_data_store import AGENT_BAR_SOURCE


def compute_dataset_hash(decision_bars: list[OHLCVBar]) -> str:
    """Deterministic sha256 over the full decision bar set (last N bars)."""
    payload: list[dict[str, object]] = []
    for bar in decision_bars:
        ts = bar.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        payload.append(
            {
                "timestamp": ts.astimezone(timezone.utc).isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _bar_to_frozen(bar: OHLCVBar) -> FrozenBarSchema:
    ts = bar.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return FrozenBarSchema(
        timestamp=ts,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        source=AGENT_BAR_SOURCE,
    )


def build_frozen_signal_decision_snapshot(
    *,
    symbol: str,
    candle_close_time: datetime,
    decision_bars: list[OHLCVBar],
    indicators: IndicatorSnapshotSchema | None,
    regime: RegimeSnapshotSchema | None,
    signal: TradingSignalSchema,
    snr: SNRSnapshotSchema | None,
    snr_state: str | None,
    agent_consensus: AgentConsensus | None,
    market_snapshot: MarketSnapshot | None,
    data_source: str = AGENT_BAR_SOURCE,
) -> SignalDecisionSnapshotSchema:
    """Assemble the immutable decision payload from in-flight pipeline state."""
    if not decision_bars:
        raise ValueError("decision_bars must not be empty")

    close_time = candle_close_time
    if close_time.tzinfo is None:
        close_time = close_time.replace(tzinfo=timezone.utc)

    return SignalDecisionSnapshotSchema(
        symbol=symbol,
        candle_close_time=close_time,
        data_source=data_source,
        bar_count=len(decision_bars),
        dataset_hash=compute_dataset_hash(decision_bars),
        snapshot_status="complete" if agent_consensus is not None else "partial",
        trigger_bar=_bar_to_frozen(decision_bars[-1]),
        indicators=indicators,
        regime=regime,
        snr=snr,
        snr_state=snr_state,
        agent_consensus=agent_consensus,
        market_snapshot=market_snapshot,
        signal=signal,
        frozen_at=datetime.now(timezone.utc),
    )


async def persist_signal_decision_snapshot(
    session: AsyncSession,
    *,
    trading_signal_id: int,
    snapshot: SignalDecisionSnapshotSchema,
) -> SignalDecisionSnapshot:
    """Insert-only persistence — snapshots are never updated."""
    row = SignalDecisionSnapshot(
        trading_signal_id=trading_signal_id,
        symbol=snapshot.symbol,
        candle_close_time=snapshot.candle_close_time,
        payload=snapshot.model_dump(mode="json"),
    )
    session.add(row)
    await session.flush()
    logger.info(
        "signal_decision_snapshot_frozen",
        trading_signal_id=trading_signal_id,
        symbol=snapshot.symbol,
        candle_close_time=snapshot.candle_close_time.isoformat(),
        bar_count=snapshot.bar_count,
        data_source=snapshot.data_source,
        snapshot_status=snapshot.snapshot_status,
        dataset_hash=snapshot.dataset_hash,
    )
    return row
