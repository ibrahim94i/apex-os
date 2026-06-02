"""Phase 3 API schemas."""

from datetime import datetime

from pydantic import BaseModel

from app.schemas import DashboardStateSchema, KillSwitchStatusSchema
from app.schemas.account import AccountModeSchema
from app.schemas.market import HourlyReportSchema, MarketStatusSchema


class RegimeBacktestStats(BaseModel):
    regime: str
    total: int
    wins: int
    losses: int
    partials: int
    win_rate: float
    avg_rr: float


class BacktestResultsSchema(BaseModel):
    symbol: str
    total_signals: int
    evaluated: int
    wins: int
    losses: int
    partials: int
    overall_win_rate: float
    overall_avg_rr: float
    by_regime: list[RegimeBacktestStats]
    best_regime: str | None
    run_at: datetime


class MemoryPatternSchema(BaseModel):
    regime: str
    time_of_day: str
    win_rate: float
    avg_rr: float
    sample_count: int


class MemorySummarySchema(BaseModel):
    symbol: str
    overall_win_rate: float = 0.0
    total_samples: int = 0
    best_regime: str | None = None
    best_regime_ar: str | None = None
    best_time_of_day: str | None = None
    best_time_of_day_ar: str | None = None


class AlertSchema(BaseModel):
    id: str
    type: str
    severity: str
    title_ar: str
    message_ar: str
    symbol: str | None = None
    timestamp: datetime
    fullscreen: bool = False


class ConfidenceBucketSchema(BaseModel):
    bucket: str
    total: int
    wins: int
    accuracy: float


class RegimePerformanceSchema(BaseModel):
    regime: str
    regime_ar: str
    total: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    expectancy: float


class PerformanceSummarySchema(BaseModel):
    total_signals: int
    evaluated_signals: int
    overall_win_rate: float
    daily_win_rate: float
    profit_factor: float
    expectancy_per_trade: float
    max_drawdown_pct: float
    best_regime: str | None
    best_regime_ar: str | None
    worst_regime: str | None
    worst_regime_ar: str | None
    by_regime: list[RegimePerformanceSchema]
    confidence_vs_accuracy: list[ConfidenceBucketSchema]
    calibration_status: str
    calibration_status_ar: str
    calibration_color: str
    run_at: datetime


class FeedStatusSchema(BaseModel):
    symbol: str
    status: str
    status_ar: str
    last_update: datetime | None = None
    age_seconds: int | None = None
    consecutive_failures: int = 0
    detail: str | None = None


class MultiAssetDashboardSchema(BaseModel):
    assets: dict[str, DashboardStateSchema]
    kill_switch: KillSwitchStatusSchema
    memory_patterns: dict[str, list[MemoryPatternSchema]] = {}
    memory_summaries: dict[str, MemorySummarySchema] = {}
    account: AccountModeSchema
    active_alerts: list[AlertSchema] = []
    market_status: dict[str, MarketStatusSchema] = {}
    feed_status: dict[str, FeedStatusSchema] = {}
    hourly_report: HourlyReportSchema | None = None
