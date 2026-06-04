"""Pydantic schemas for API request/response."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.agent import AgentConsensus, AgentVerdict, MarketSnapshot
from app.schemas.market import HourlyReportSchema, MarketStatusSchema
from app.schemas.enums import KillSwitchStatus, RegimeType, SignalDirection
from app.schemas.snapshots import (
    IndicatorSnapshotSchema,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
)

__all__ = [
    "AgentConsensus",
    "AgentVerdict",
    "MarketSnapshot",
    "SignalDirection",
    "RegimeType",
    "KillSwitchStatus",
    "PriceBarSchema",
    "IndicatorSnapshotSchema",
    "RegimeSnapshotSchema",
    "TradingSignalSchema",
    "KillSwitchStatusSchema",
    "DashboardStateSchema",
    "HealthResponse",
    "MarketStatusSchema",
    "HourlyReportSchema",
]


class PriceBarSchema(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: str = "binance"


class TradingSignalSchema(BaseModel):
    id: int | None = None
    symbol: str
    timestamp: datetime
    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float = 0.0
    regime: RegimeType
    degraded: bool = False
    degradation_reason: str | None = None
    kill_switch_active: bool = False


class DashboardStateSchema(BaseModel):
    regime: RegimeSnapshotSchema | None = None
    latest_signal: TradingSignalSchema | None = None
    kill_switch: KillSwitchStatusSchema
    signal_history: list[TradingSignalSchema] = []
    current_price: float | None = None
    symbol: str = "XAUUSD"
    agent_consensus: AgentConsensus | None = None
    market_status: MarketStatusSchema | None = None


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: str
    redis: str
