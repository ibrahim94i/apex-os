"""Trading journal and position manager schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


FollowUpAction = Literal["entered", "lost", "ignored"]


class JournalEntryCreateSchema(BaseModel):
    symbol: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    source: Literal["system_signal", "personal"]
    emotion: Literal["confident", "hesitant", "fearful"]
    result: Literal["win", "loss", "neutral"]
    notes: str | None = None


class JournalFollowUpSchema(BaseModel):
    """User response to a pending Telegram signal journal row."""

    action: FollowUpAction
    exit_price: float | None = Field(default=None, gt=0)
    result: Literal["win", "loss"] | None = None

    @model_validator(mode="after")
    def validate_action_fields(self) -> "JournalFollowUpSchema":
        if self.action == "ignored":
            return self
        if self.exit_price is None:
            raise ValueError("exit_price required for entered and lost")
        if self.action == "entered" and self.result is None:
            raise ValueError("result required when action is entered")
        return self


class JournalEntrySchema(BaseModel):
    id: int
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    source: str
    emotion: str
    result: str
    follow_up_status: str
    signal_confidence: float | None = None
    snr_state: str | None = None
    snr_penalty: int | None = None
    notes: str | None
    pnl: float
    pnl_pct: float
    closed_at: datetime
    created_at: datetime | None = None


class JournalSnrAnalyticsSchema(BaseModel):
    inside_zone_win_rate: float
    inside_zone_resolved: int
    outside_zone_win_rate: float
    outside_zone_resolved: int
    generated_at: datetime


class JournalSignalReportSchema(BaseModel):
    total_signals: int
    entered_count: int
    ignored_count: int
    lost_count: int
    pending_count: int
    win_rate: float
    total_profit: float
    total_loss: float
    net_pnl: float
    generated_at: datetime


class JournalAnalysisSchema(BaseModel):
    total_trades: int
    win_rate: float
    best_time_of_day: str
    best_time_of_day_ar: str
    system_losses: int
    personal_losses: int
    worse_source_ar: str
    fearful_losses: int
    confident_losses: int
    worse_emotion_ar: str
    recommendation_ar: str
    generated_at: datetime
    signal_report: JournalSignalReportSchema | None = None
    snr_analytics: JournalSnrAnalyticsSchema | None = None


class PositionManagerSchema(BaseModel):
    account_balance: float
    daily_loss_limit_usd: float
    daily_loss_used_usd: float
    daily_loss_remaining_usd: float
    risk_per_trade_usd: float
    losing_trades_today: int
    additional_trades_allowed: int
    market_state_ar: str
    can_trade: bool
    message_ar: str
