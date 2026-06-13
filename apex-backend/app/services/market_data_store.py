"""Load market data from PostgreSQL when TwelveData API is unavailable."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select

from app.database import AsyncSessionLocal
from app.models import PriceBar, RegimeSnapshot


def _bar_to_dict(row: PriceBar) -> dict[str, Any]:
    ts = row.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return {
        "symbol": row.symbol,
        "timestamp": ts.isoformat(),
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "volume": row.volume,
        "source": row.source,
        "is_closed": True,
    }


async def fetch_bars_from_db(symbol: str, limit: int = 250) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PriceBar)
            .where(PriceBar.symbol == symbol)
            .order_by(desc(PriceBar.timestamp))
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
    return [_bar_to_dict(row) for row in rows]


async def count_bars_in_db(symbol: str) -> int:
    from sqlalchemy import func

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count())
            .select_from(PriceBar)
            .where(PriceBar.symbol == symbol)
        )
        return int(result.scalar_one())


async def get_oldest_bar_timestamp(symbol: str) -> datetime | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PriceBar.timestamp)
            .where(PriceBar.symbol == symbol)
            .order_by(PriceBar.timestamp.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def persist_bars_batch(bars: list[dict[str, Any]]) -> int:
    """Insert historical bars; skip duplicates. Returns rows attempted."""
    if not bars:
        return 0
    from sqlalchemy.dialects.postgresql import insert

    from app.models import PriceBar

    values = []
    for bar in bars:
        ts = bar["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        values.append(
            {
                "symbol": bar["symbol"],
                "source": bar.get("source", "unknown"),
                "timestamp": ts,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar.get("volume", 0.0),
            }
        )

    async with AsyncSessionLocal() as session:
        stmt = insert(PriceBar).values(values).on_conflict_do_nothing(
            index_elements=["symbol", "timestamp"]
        )
        await session.execute(stmt)
        await session.commit()
    return len(values)


async def upsert_metatrader_bar(bar: dict[str, Any]) -> None:
    """Insert or replace an H1 bar from MetaTrader (overrides Binance at same timestamp)."""
    from sqlalchemy.dialects.postgresql import insert

    ts = bar["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    values = {
        "symbol": bar["symbol"],
        "source": bar.get("source", "metatrader"),
        "timestamp": ts,
        "open": bar["open"],
        "high": bar["high"],
        "low": bar["low"],
        "close": bar["close"],
        "volume": bar.get("volume", 0.0),
    }

    async with AsyncSessionLocal() as session:
        stmt = insert(PriceBar).values(values).on_conflict_do_update(
            index_elements=["symbol", "timestamp"],
            set_={
                "source": values["source"],
                "open": values["open"],
                "high": values["high"],
                "low": values["low"],
                "close": values["close"],
                "volume": values["volume"],
            },
        )
        await session.execute(stmt)
        await session.commit()


async def get_latest_price_from_db(symbol: str) -> dict[str, Any] | None:
    bars = await fetch_bars_from_db(symbol, limit=1)
    if not bars:
        return None
    bar = bars[-1]
    return {"price": bar["close"], "timestamp": bar["timestamp"]}


async def get_latest_regime_from_db(symbol: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RegimeSnapshot)
            .where(RegimeSnapshot.symbol == symbol)
            .order_by(desc(RegimeSnapshot.timestamp))
            .limit(1)
        )
        row = result.scalar_one_or_none()
    if row is None:
        return None
    ts = row.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return {
        "symbol": row.symbol,
        "timestamp": ts.isoformat(),
        "regime": row.regime.value,
        "confidence": row.confidence,
        "adx_value": row.adx_value,
        "volatility_pct": row.volatility_pct,
        "trend_strength": row.trend_strength,
    }
