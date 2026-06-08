"""Support / Resistance (SNR) snapshot schema."""

from datetime import datetime

from pydantic import BaseModel, Field


class SNRLevelZone(BaseModel):
    level: float
    low: float
    high: float


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
    support_1_zone: SNRLevelZone | None = None
    support_2_zone: SNRLevelZone | None = None
    support_3_zone: SNRLevelZone | None = None
    resistance_1_zone: SNRLevelZone | None = None
    resistance_2_zone: SNRLevelZone | None = None
    resistance_3_zone: SNRLevelZone | None = None
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
