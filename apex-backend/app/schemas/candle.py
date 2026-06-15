"""MetaTrader H1 candle ingest schemas."""

from pydantic import BaseModel, Field


class MetaTraderCandleUpdateResponse(BaseModel):
    ok: bool = True
    symbol: str
    timeframe: str = "H1"
    timestamp: str
    source: str = "metatrader"
    received_at: str
    pipeline_ran: bool = False


class MetaTraderCandleBootstrapResponse(BaseModel):
    ok: bool = True
    symbol: str
    timeframe: str = "H1"
    source: str = "metatrader"
    received_at: str
    upserted: int
    deleted: int
    oldest: str | None = None
    newest: str | None = None
