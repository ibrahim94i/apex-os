"""Trading journal ORM models."""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TradeSource(str, PyEnum):
    SYSTEM = "system_signal"
    PERSONAL = "personal"


class EntryEmotion(str, PyEnum):
    CONFIDENT = "confident"
    HESITANT = "hesitant"
    FEARFUL = "fearful"


class JournalResult(str, PyEnum):
    WIN = "win"
    LOSS = "loss"
    NEUTRAL = "neutral"


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    emotion: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
