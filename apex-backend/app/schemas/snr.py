"""Support / Resistance (SNR) snapshot schema."""

from datetime import datetime

from pydantic import BaseModel, Field


class SNRSnapshotSchema(BaseModel):
    symbol: str
    timestamp: datetime
    price: float
    support_1: float | None = None
    support_2: float | None = None
    support_3: float | None = None
    resistance_1: float | None = None
    resistance_2: float | None = None
    resistance_3: float | None = None
    distance_to_support_pct: float | None = Field(
        default=None,
        description="Percent distance from price to nearest support (S1)",
    )
    distance_to_resistance_pct: float | None = Field(
        default=None,
        description="Percent distance from price to nearest resistance (R1)",
    )
    pivot_high_count: int = 0
    pivot_low_count: int = 0
