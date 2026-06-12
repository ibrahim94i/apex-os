"""Price layer schemas — MetaTrader ingest (display only, no trading)."""

from datetime import datetime

from pydantic import BaseModel, Field


class MetaTraderPriceUpdate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    time: datetime


class MetaTraderPriceUpdateResponse(BaseModel):
    ok: bool = True
    symbol: str
    price: float
    bid: float
    ask: float
    price_source: str = "metatrader"
    received_at: str


class MetaTraderHealthStatus(BaseModel):
    symbol: str
    status: str
    status_ar: str
    connected: bool
    price_source: str | None = None
    last_update: str | None = None
    age_seconds: int | None = None
    bid: float | None = None
    ask: float | None = None
    price: float | None = None
