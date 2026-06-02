"""Market snapshot schemas shared across API and agents."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.enums import KillSwitchStatus, RegimeType, SignalDirection


class IndicatorSnapshotSchema(BaseModel):
    symbol: str
    timestamp: datetime
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    ema_9: float | None = None
    ema_21: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    atr: float | None = None
    atr_avg_20: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    adx: float | None = None


class RegimeSnapshotSchema(BaseModel):
    symbol: str
    timestamp: datetime
    regime: RegimeType
    confidence: float = Field(ge=0.0, le=1.0)
    adx_value: float | None = None
    volatility_pct: float | None = None
    trend_strength: float | None = None


class KillSwitchStatusSchema(BaseModel):
    status: KillSwitchStatus
    reason: str | None = None
    triggered_at: datetime | None = None
    drawdown_pct: float | None = None
    daily_loss_pct: float | None = None
    consecutive_losses: int | None = None
