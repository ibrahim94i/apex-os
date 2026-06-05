"""Smart Advisor (المستشار الذكي) request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class AdvisorMessage(BaseModel):
    role: str = Field(description="user or assistant")
    content: str


class AdvisorChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    symbol: str | None = Field(
        default=None,
        description="Optional focus asset; advisor still receives all APEX data",
    )
    history: list[AdvisorMessage] = Field(default_factory=list, max_length=20)


class AdvisorAssetContext(BaseModel):
    symbol: str
    display_name_ar: str
    price: float | None = None
    apex_price: float | None = None
    price_timestamp: datetime | None = None
    price_age_minutes: float | None = None
    apex_price_stale: bool = False
    price_source: str | None = None
    feed_type: str | None = None
    regime: str | None = None
    regime_confidence: float | None = None
    adx: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    ema_9: float | None = None
    ema_21: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    agent_direction: str | None = None
    agent_confidence: float | None = None
    agent_summary: str | None = None
    latest_signal_direction: str | None = None
    latest_signal_confidence: float | None = None
    news_count: int = 0
    data_complete: bool = True


class AdvisorChatResponse(BaseModel):
    reply: str
    symbol: str | None = None
    model: str
    latency_ms: float
    web_search_used: bool = False
    apex_context: list[AdvisorAssetContext] = Field(default_factory=list)
    timestamp: datetime


class AdvisorContextResponse(BaseModel):
    assets: list[AdvisorAssetContext]
    timestamp: datetime
