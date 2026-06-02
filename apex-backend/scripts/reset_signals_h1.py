"""Delete old signals and related data — fresh start for H1 pipeline."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select

from app.config.assets import ACTIVE_SYMBOLS
from app.core.redis_client import CacheKeys, close_redis, get_redis
from app.database import AsyncSessionLocal
from app.models import IndicatorSnapshot, PriceBar, RegimeSnapshot, TradeResult, TradingSignal
from app.models.phase3 import AgentWeightLog, MemoryPattern

SYMBOL = "XAUUSD"


async def reset_xauusd() -> None:
    async with AsyncSessionLocal() as session:
        counts = {
            "signals": (
                await session.execute(
                    select(func.count())
                    .select_from(TradingSignal)
                    .where(TradingSignal.symbol == SYMBOL)
                )
            ).scalar_one(),
            "price_bars": (
                await session.execute(
                    select(func.count())
                    .select_from(PriceBar)
                    .where(PriceBar.symbol == SYMBOL)
                )
            ).scalar_one(),
            "indicators": (
                await session.execute(
                    select(func.count())
                    .select_from(IndicatorSnapshot)
                    .where(IndicatorSnapshot.symbol == SYMBOL)
                )
            ).scalar_one(),
            "regimes": (
                await session.execute(
                    select(func.count())
                    .select_from(RegimeSnapshot)
                    .where(RegimeSnapshot.symbol == SYMBOL)
                )
            ).scalar_one(),
            "memory": (
                await session.execute(
                    select(func.count())
                    .select_from(MemoryPattern)
                    .where(MemoryPattern.symbol == SYMBOL)
                )
            ).scalar_one(),
        }

        await session.execute(delete(TradeResult).where(TradeResult.symbol == SYMBOL))
        await session.execute(delete(MemoryPattern).where(MemoryPattern.symbol == SYMBOL))
        await session.execute(delete(AgentWeightLog).where(AgentWeightLog.symbol == SYMBOL))
        await session.execute(delete(TradingSignal).where(TradingSignal.symbol == SYMBOL))
        await session.execute(
            delete(IndicatorSnapshot).where(IndicatorSnapshot.symbol == SYMBOL)
        )
        await session.execute(delete(RegimeSnapshot).where(RegimeSnapshot.symbol == SYMBOL))
        await session.execute(delete(PriceBar).where(PriceBar.symbol == SYMBOL))
        await session.commit()

    redis = await get_redis()
    keys = [
        CacheKeys.LATEST_SIGNAL.format(symbol=SYMBOL),
        CacheKeys.SIGNAL_HISTORY.format(symbol=SYMBOL),
        CacheKeys.DASHBOARD_STATE.format(symbol=SYMBOL),
        CacheKeys.AGENT_CONSENSUS.format(symbol=SYMBOL),
        CacheKeys.LATEST_INDICATORS.format(symbol=SYMBOL),
        CacheKeys.LATEST_REGIME.format(symbol=SYMBOL),
        CacheKeys.LATEST_PRICE.format(symbol=SYMBOL),
    ]
    deleted_keys = await redis.delete(*keys)
    await close_redis()

    print(f"=== XAUUSD reset complete ===")
    for label, n in counts.items():
        print(f"  {label}: {n} deleted")
    print(f"  redis_keys: {deleted_keys}")


async def reset_signals_h1() -> None:
    async with AsyncSessionLocal() as session:
        counts = {
            "signals": (
                await session.execute(select(func.count()).select_from(TradingSignal))
            ).scalar_one(),
            "price_bars": (
                await session.execute(select(func.count()).select_from(PriceBar))
            ).scalar_one(),
            "indicators": (
                await session.execute(select(func.count()).select_from(IndicatorSnapshot))
            ).scalar_one(),
            "regimes": (
                await session.execute(select(func.count()).select_from(RegimeSnapshot))
            ).scalar_one(),
            "memory": (
                await session.execute(select(func.count()).select_from(MemoryPattern))
            ).scalar_one(),
            "trades": (
                await session.execute(select(func.count()).select_from(TradeResult))
            ).scalar_one(),
        }

        await session.execute(delete(TradeResult))
        await session.execute(delete(MemoryPattern))
        await session.execute(delete(AgentWeightLog))
        await session.execute(delete(TradingSignal))
        await session.execute(delete(IndicatorSnapshot))
        await session.execute(delete(RegimeSnapshot))
        await session.execute(delete(PriceBar))
        await session.commit()

    redis = await get_redis()
    keys: list[str] = [CacheKeys.HOURLY_REPORT, CacheKeys.KILL_SWITCH]
    for sym in ACTIVE_SYMBOLS:
        keys.extend(
            [
                CacheKeys.LATEST_SIGNAL.format(symbol=sym),
                CacheKeys.SIGNAL_HISTORY.format(symbol=sym),
                CacheKeys.DASHBOARD_STATE.format(symbol=sym),
                CacheKeys.AGENT_CONSENSUS.format(symbol=sym),
                CacheKeys.LATEST_INDICATORS.format(symbol=sym),
                CacheKeys.LATEST_REGIME.format(symbol=sym),
                CacheKeys.LATEST_PRICE.format(symbol=sym),
            ]
        )
    deleted_keys = await redis.delete(*keys)
    await close_redis()

    print("=== APEX H1 reset complete ===")
    for label, n in counts.items():
        print(f"  {label}: {n} deleted")
    print(f"  redis_keys: {deleted_keys}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "xauusd":
        asyncio.run(reset_xauusd())
    else:
        asyncio.run(reset_signals_h1())
