"""Trading journal and position manager schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    notes: str | None
    pnl: float
    pnl_pct: float
    closed_at: datetime


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
