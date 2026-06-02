"""Pydantic contracts for the multi-agent system."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.enums import SignalDirection
from app.schemas.snapshots import (
    IndicatorSnapshotSchema,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
)


class AgentRole(str, Enum):
    MARKET_ANALYST = "market_analyst"
    RISK = "risk"
    NEWS = "news"


class AgentLLMOutput(BaseModel):
    """Structured JSON contract returned by each agent LLM call."""

    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: list[str] = Field(min_length=1, max_length=15)


class CombinedAgentLLMOutput(BaseModel):
    """Single Groq response covering all three agents."""

    market_analyst: AgentLLMOutput
    risk: AgentLLMOutput
    news: AgentLLMOutput


class MarketSnapshot(BaseModel):
    """Unified market context fed to all agents."""

    symbol: str
    timestamp: datetime
    price: float
    indicators: IndicatorSnapshotSchema
    regime: RegimeSnapshotSchema
    kill_switch: KillSwitchStatusSchema
    account_balance: float
    max_risk_pct: float
    max_drawdown_pct: float
    daily_loss_pct: float = 0.0
    consecutive_losses: int = 0
    feed_stale: bool = False
    memory_patterns: list[dict[str, object]] = Field(default_factory=list)


class AgentVerdict(BaseModel):
    """Final output from a single agent."""

    agent_id: AgentRole
    agent_name_ar: str
    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: list[str] = Field(max_length=15)
    weight: float = Field(ge=0.0, le=1.0)
    latency_ms: float | None = None
    used_llm: bool = False
    error: str | None = None


class AgentConsensus(BaseModel):
    """Weighted voting result across all agents."""

    symbol: str
    timestamp: datetime
    final_direction: SignalDirection
    final_confidence: float = Field(ge=0.0, le=1.0)
    verdicts: list[AgentVerdict]
    vote_scores: dict[str, float]
    reasoning_summary: list[str] = Field(default_factory=list, max_length=15)
