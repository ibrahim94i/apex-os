"""Pydantic contracts for the multi-agent system."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRSnapshotSchema
from app.schemas.snapshots import (
    IndicatorSnapshotSchema,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
)


class AgentRole(str, Enum):
    MARKET_ANALYST = "market_analyst"
    RISK = "risk"
    NEWS = "news"


class CandlestickPatternSchema(BaseModel):
    """Detected candlestick pattern on a recent closed bar."""

    pattern: str
    name_ar: str
    signal: Literal["bullish", "bearish", "neutral"]
    bar_offset: int = Field(
        0,
        ge=0,
        description="0 = latest closed candle, 1 = previous, etc.",
    )
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="pandas", description="pandas or TA-Lib")


class EconomicEventSchema(BaseModel):
    """High-impact economic calendar event (Finnhub)."""

    event: str
    country: str = ""
    impact: str = "high"
    event_time: datetime
    estimate: float | None = None
    previous: float | None = None
    actual: float | None = None
    unit: str = ""


class NewsHeadline(BaseModel):
    """Multi-source headline fed to the news agent."""

    headline: str
    summary: str = ""
    source: str = ""
    provider: str = ""
    url: str = ""
    category: str = ""
    published_at: datetime | None = None
    sentiment_score: float | None = Field(
        default=None,
        description="Normalized sentiment -1.0 (bearish) to +1.0 (bullish)",
    )
    sentiment_label: str = Field(
        default="",
        description="Bullish/Bearish/Neutral or Arabic equivalent",
    )


class AgentLLMOutput(BaseModel):
    """Structured JSON contract returned by each agent LLM call."""

    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: list[str] = Field(min_length=1, max_length=15)


class NewsAgentLLMOutput(AgentLLMOutput):
    """Extended news agent output with per-asset impact analysis."""

    asset_impacts: dict[str, Literal["positive", "negative", "neutral"]] = Field(
        default_factory=dict,
        description="Impact on XAUUSD, EURUSD, USDJPY, GBPUSD",
    )
    overall_risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    recommendation_ar: str = Field(
        default="",
        description="Clear trading recommendation based on news only",
    )


class CombinedAgentLLMOutput(BaseModel):
    """Single Groq response covering all three agents."""

    market_analyst: AgentLLMOutput
    risk: AgentLLMOutput
    news: NewsAgentLLMOutput


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
    candlestick_patterns: list[CandlestickPatternSchema] = Field(default_factory=list)
    news_headlines: list[NewsHeadline] = Field(default_factory=list)
    upcoming_events: list[EconomicEventSchema] = Field(default_factory=list)
    snr: SNRSnapshotSchema | None = None


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
    analyzed_at: datetime | None = None
    is_stale: bool = False
    data_age_seconds: float | None = None


class TeamRoundOpinion(BaseModel):
    """Single agent opinion in a discussion round."""

    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: list[str] = Field(min_length=1, max_length=10)


class TeamDiscussionLLMOutput(BaseModel):
    """Three-round team discussion — single LLM JSON response."""

    round1_initial: dict[str, TeamRoundOpinion]
    round2_responses: dict[str, TeamRoundOpinion]
    round3_final: TeamRoundOpinion
    agreements: list[str] = Field(default_factory=list, max_length=10)
    disagreements: list[str] = Field(default_factory=list, max_length=10)
    discussion_summary: list[str] = Field(default_factory=list, max_length=15)


class AgentConsensus(BaseModel):
    """Weighted voting result across all agents."""

    symbol: str
    timestamp: datetime
    final_direction: SignalDirection
    final_confidence: float = Field(ge=0.0, le=1.0)
    verdicts: list[AgentVerdict]
    vote_scores: dict[str, float]
    reasoning_summary: list[str] = Field(default_factory=list, max_length=15)
    team_discussion: TeamDiscussionLLMOutput | None = None
    discussion_summary_ar: list[str] = Field(default_factory=list, max_length=20)
    signal_decision: str | None = None  # emitted | blocked | wait | none
    rejection_reason: str | None = None
    rejection_reason_ar: str | None = None
    proposed_direction: SignalDirection | None = None
    proposed_confidence: float | None = None
    snr_state: str | None = None  # INSIDE_ZONE | ZONE_EDGE | BREAKOUT_CONFIRMED | NORMAL
    snr_state_ar: str | None = None
    snr_warning_ar: str | None = None
    final_decision: str | None = None  # NO_TRADE | BUY | SELL
    final_decision_ar: str | None = None
    llm_provider: str | None = None
    is_stale: bool = False
    stale_warning_ar: str | None = None

    def is_llm_powered(self) -> bool:
        """True when all verdicts used the LLM (not rule-based fallback)."""
        return bool(self.verdicts) and all(v.used_llm for v in self.verdicts)

    def is_groq_powered(self) -> bool:
        """Backward-compatible alias for is_llm_powered."""
        return self.is_llm_powered()
