"""Load market data from PostgreSQL when TwelveData API is unavailable."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, desc, select

from app.database import AsyncSessionLocal
from app.models import ChartBar, PriceBar, RegimeSnapshot

METATRADER_BAR_SOURCE = "metatrader"
AGENT_BAR_SOURCE = METATRADER_BAR_SOURCE


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


async def fetch_bars_from_db(
    symbol: str,
    limit: int = 250,
    *,
    source: str | None = None,
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        query = select(PriceBar).where(PriceBar.symbol == symbol)
        if source is not None:
            query = query.where(PriceBar.source == source)
        result = await session.execute(
            query.order_by(desc(PriceBar.timestamp)).limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
    return [_bar_to_dict(row) for row in rows]


async def fetch_agent_bars_from_db(symbol: str, limit: int = 500) -> list[dict[str, Any]]:
    """H1 bars for SNR, agents, and signals — MetaTrader broker candles only."""
    return await fetch_bars_from_db(symbol, limit, source=AGENT_BAR_SOURCE)


async def purge_non_metatrader_price_bars(symbol: str) -> int:
    """Remove all non-MetaTrader rows from price_bars for a symbol."""
    async with AsyncSessionLocal() as session:
        delete_result = await session.execute(
            delete(PriceBar).where(
                PriceBar.symbol == symbol,
                PriceBar.source != METATRADER_BAR_SOURCE,
            )
        )
        deleted = int(delete_result.rowcount or 0)
        await session.commit()
    return deleted


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

    from app.services.price_bar_guard import (
        log_blocked_external_bar,
        should_block_external_price_bars,
    )

    symbol = str(bars[0].get("symbol", ""))
    if symbol and await should_block_external_price_bars(symbol):
        source = str(bars[0].get("source", "unknown"))
        await log_blocked_external_bar(symbol, source, context="persist_bars_batch")
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


def _coerce_bar_timestamp(value: datetime | str) -> datetime:
    ts = value
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


async def bootstrap_metatrader_h1_bars(
    symbol: str,
    parsed_bars: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace all non-MetaTrader H1 rows, then upsert MT bootstrap history."""
    from sqlalchemy.dialects.postgresql import insert

    if not parsed_bars:
        return {"upserted": 0, "deleted": 0, "purged": 0, "oldest": None, "newest": None}

    purged = await purge_non_metatrader_price_bars(symbol)

    values: list[dict[str, Any]] = []
    for parsed in parsed_bars:
        ts = _coerce_bar_timestamp(parsed["timestamp"])
        values.append(
            {
                "symbol": symbol,
                "source": "metatrader",
                "timestamp": ts,
                "open": parsed["open"],
                "high": parsed["high"],
                "low": parsed["low"],
                "close": parsed["close"],
                "volume": parsed.get("volume", 0.0),
            }
        )

    values.sort(key=lambda row: row["timestamp"])
    min_ts = values[0]["timestamp"]
    max_ts = values[-1]["timestamp"]

    async with AsyncSessionLocal() as session:
        delete_result = await session.execute(
            delete(PriceBar).where(
                PriceBar.symbol == symbol,
                PriceBar.source != "metatrader",
                PriceBar.timestamp >= min_ts,
                PriceBar.timestamp <= max_ts,
            )
        )
        deleted = int(delete_result.rowcount or 0)

        stmt = insert(PriceBar).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "timestamp"],
            set_={
                "source": stmt.excluded.source,
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        await session.execute(stmt)
        await session.commit()

    return {
        "upserted": len(values),
        "deleted": deleted,
        "purged": purged,
        "oldest": min_ts.isoformat(),
        "newest": max_ts.isoformat(),
    }


async def upsert_chart_bar(timeframe: str, bar: dict[str, Any]) -> None:
    """Insert or replace a chart-only bar from MetaTrader."""
    from sqlalchemy.dialects.postgresql import insert

    ts = bar["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    values = {
        "symbol": bar["symbol"],
        "timeframe": timeframe,
        "source": bar.get("source", "metatrader"),
        "timestamp": ts,
        "open": bar["open"],
        "high": bar["high"],
        "low": bar["low"],
        "close": bar["close"],
        "volume": bar.get("volume", 0.0),
    }

    async with AsyncSessionLocal() as session:
        stmt = insert(ChartBar).values(values).on_conflict_do_update(
            index_elements=["symbol", "timeframe", "timestamp"],
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


async def fetch_chart_bars_from_db(
    symbol: str,
    timeframe: str,
    limit: int = 250,
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ChartBar)
            .where(ChartBar.symbol == symbol, ChartBar.timeframe == timeframe)
            .order_by(desc(ChartBar.timestamp))
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))

    bars: list[dict[str, Any]] = []
    for row in rows:
        ts = row.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        bars.append(
            {
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
        )
    return bars


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
