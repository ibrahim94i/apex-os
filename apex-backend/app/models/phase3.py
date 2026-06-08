"""Phase 3 schema additions: outcomes, memory patterns, weight logs."""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SignalOutcome(str, PyEnum):
    WIN = "WIN"
    LOSS = "LOSS"
    PARTIAL = "PARTIAL"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"


class TimeOfDay(str, PyEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class MemoryPattern(Base):
    __tablename__ = "memory_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    regime: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    time_of_day: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_rr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AgentWeightLog(Base):
    __tablename__ = "agent_weight_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    regime: Mapped[str] = mapped_column(String(32), nullable=False)
    market_weight: Mapped[float] = mapped_column(Float, nullable=False)
    risk_weight: Mapped[float] = mapped_column(Float, nullable=False)
    news_weight: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
