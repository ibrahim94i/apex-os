"""Immutable decision snapshot captured when a signal is emitted."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import TradingSignalSchema
from app.schemas.agent import AgentConsensus, MarketSnapshot
from app.schemas.snr import SNRSnapshotSchema
from app.schemas.snapshots import IndicatorSnapshotSchema, RegimeSnapshotSchema


class FrozenBarSchema(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: str = "metatrader"


class SignalDecisionSnapshotSchema(BaseModel):
    """Single immutable record of all inputs used for one emitted signal."""

    symbol: str
    candle_close_time: datetime
    data_source: str = "metatrader"
    bar_count: int
    dataset_hash: str = Field(description="sha256 of canonical last-N decision bars JSON")
    snapshot_status: Literal["complete", "partial"] = Field(
        description="complete when agent_consensus present, partial otherwise"
    )
    trigger_bar: FrozenBarSchema
    indicators: IndicatorSnapshotSchema | None = None
    regime: RegimeSnapshotSchema | None = None
    snr: SNRSnapshotSchema | None = None
    snr_state: str | None = None
    agent_consensus: AgentConsensus | None = None
    market_snapshot: MarketSnapshot | None = None
    signal: TradingSignalSchema
    frozen_at: datetime = Field(description="Wall-clock time when snapshot was persisted")
