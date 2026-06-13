"""Market status and countdown schemas."""

from datetime import datetime

from pydantic import BaseModel


class MarketStatusSchema(BaseModel):
    symbol: str
    is_open: bool
    timezone: str = "Asia/Baghdad"
    schedule_ar: str
    next_open_at: datetime | None = None
    next_close_at: datetime | None = None
    next_signal_at: datetime | None = None
    seconds_until_open: int | None = None
    seconds_until_close: int | None = None
    seconds_until_next_signal: int | None = None


class HourlyReportAssetSchema(BaseModel):
    symbol: str
    display_name_ar: str
    is_market_open: bool
    market_direction: str
    last_signal_direction: str | None = None
    last_signal_confidence_pct: float | None = None
    agent_recommendation: str | None = None
    agent_confidence_pct: float | None = None
    summary_ar: str


class HourlyReportSchema(BaseModel):
    timestamp: datetime
    assets: list[HourlyReportAssetSchema]
