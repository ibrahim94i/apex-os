"""Memory engine — PostgreSQL patterns + Redis cache for agents."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.assets import ACTIVE_SYMBOLS
from app.core.redis_client import cache_get, cache_set
from app.database import AsyncSessionLocal
from app.models import TradingSignal
from app.models.phase3 import MemoryPattern, TimeOfDay
from app.logging_config import logger
from app.websocket.manager import broadcaster

REDIS_TOP_PATTERNS_KEY = "apex:memory:top_patterns:{symbol}"
REDIS_SUMMARY_KEY = "apex:memory:summary:{symbol}"

TIME_AR = {
    "morning": "صباحاً",
    "afternoon": "ظهراً",
    "evening": "مساءً",
    "night": "ليلاً",
}

REGIME_AR = {
    "TRENDING_UP": "اتجاه صاعد",
    "TRENDING_DOWN": "اتجاه هابط",
    "RANGING": "سوق جانبي",
    "VOLATILE": "تذبذب عالي",
    "UNKNOWN": "غير معروف",
}


def time_of_day(hour: int) -> str:
    if 6 <= hour < 12:
        return TimeOfDay.MORNING.value
    if 12 <= hour < 17:
        return TimeOfDay.AFTERNOON.value
    if 17 <= hour < 22:
        return TimeOfDay.EVENING.value
    return TimeOfDay.NIGHT.value


class MemoryEngine:
    TOP_N = 5

    async def update_from_signals(self, session: AsyncSession, symbol: str | None = None) -> int:
        query = select(TradingSignal).where(TradingSignal.outcome.in_(["WIN", "LOSS"]))
        if symbol:
            query = query.where(TradingSignal.symbol == symbol)
        result = await session.execute(query)
        signals = result.scalars().all()

        buckets: dict[tuple[str, str, str], dict[str, Any]] = {}

        for sig in signals:
            regime = sig.regime.value if hasattr(sig.regime, "value") else str(sig.regime)
            tod = time_of_day(sig.timestamp.hour)
            key = (sig.symbol, regime, tod)

            if key not in buckets:
                buckets[key] = {"wins": 0, "total": 0, "rr_sum": 0.0}
            bucket = buckets[key]
            bucket["total"] += 1
            if sig.outcome == "WIN":
                bucket["wins"] += 1
            bucket["rr_sum"] += sig.rr_achieved or 0.0

        updated = 0
        for (sym, regime, tod), bucket in buckets.items():
            win_rate = bucket["wins"] / bucket["total"] if bucket["total"] else 0.0
            avg_rr = bucket["rr_sum"] / bucket["total"] if bucket["total"] else 0.0

            existing = await session.execute(
                select(MemoryPattern).where(
                    MemoryPattern.symbol == sym,
                    MemoryPattern.regime == regime,
                    MemoryPattern.time_of_day == tod,
                    MemoryPattern.agent_id.is_(None),
                )
            )
            pattern = existing.scalar_one_or_none()
            if pattern:
                pattern.win_rate = round(win_rate, 4)
                pattern.avg_rr = round(avg_rr, 4)
                pattern.sample_count = bucket["total"]
                pattern.updated_at = datetime.now(timezone.utc)
            else:
                session.add(
                    MemoryPattern(
                        symbol=sym,
                        regime=regime,
                        time_of_day=tod,
                        agent_id=None,
                        win_rate=round(win_rate, 4),
                        avg_rr=round(avg_rr, 4),
                        sample_count=bucket["total"],
                    )
                )
            updated += 1

        await session.commit()

        symbols = {sym for sym, _, _ in buckets.keys()}
        if symbol:
            symbols.add(symbol)
        for sym in symbols:
            await self._cache_top_patterns(session, sym)
            await self._cache_summary(session, sym)

        logger.info("memory_patterns_updated", count=updated, symbols=list(symbols))
        return updated

    async def _cache_top_patterns(self, session: AsyncSession, symbol: str) -> None:
        result = await session.execute(
            select(MemoryPattern)
            .where(MemoryPattern.symbol == symbol, MemoryPattern.agent_id.is_(None))
            .order_by(MemoryPattern.win_rate.desc(), MemoryPattern.sample_count.desc())
            .limit(self.TOP_N)
        )
        patterns = result.scalars().all()
        data = [
            {
                "regime": p.regime,
                "time_of_day": p.time_of_day,
                "win_rate": p.win_rate,
                "avg_rr": p.avg_rr,
                "sample_count": p.sample_count,
            }
            for p in patterns
        ]
        await cache_set(REDIS_TOP_PATTERNS_KEY.format(symbol=symbol), data, ttl=3600)

    async def _cache_summary(self, session: AsyncSession, symbol: str) -> None:
        summary = await self._build_summary(session, symbol)
        await cache_set(REDIS_SUMMARY_KEY.format(symbol=symbol), summary, ttl=3600)

    async def _build_summary(self, session: AsyncSession, symbol: str) -> dict[str, Any]:
        result = await session.execute(
            select(TradingSignal).where(
                TradingSignal.symbol == symbol,
                TradingSignal.outcome.in_(["WIN", "LOSS"]),
            )
        )
        signals = result.scalars().all()
        if not signals:
            return {
                "symbol": symbol,
                "overall_win_rate": 0.0,
                "total_samples": 0,
                "best_regime": None,
                "best_regime_ar": None,
                "best_time_of_day": None,
                "best_time_of_day_ar": None,
            }

        wins = sum(1 for s in signals if s.outcome == "WIN")
        overall_win_rate = wins / len(signals)

        regime_stats: dict[str, dict[str, int]] = {}
        time_stats: dict[str, dict[str, int]] = {}
        for sig in signals:
            regime = sig.regime.value if hasattr(sig.regime, "value") else str(sig.regime)
            tod = time_of_day(sig.timestamp.hour)
            for bucket, key in ((regime_stats, regime), (time_stats, tod)):
                if key not in bucket:
                    bucket[key] = {"wins": 0, "total": 0}
                bucket[key]["total"] += 1
                if sig.outcome == "WIN":
                    bucket[key]["wins"] += 1

        def best_key(stats: dict[str, dict[str, int]]) -> str | None:
            eligible = {k: v for k, v in stats.items() if v["total"] >= 1}
            if not eligible:
                return None
            return max(eligible, key=lambda k: eligible[k]["wins"] / eligible[k]["total"])

        best_regime = best_key(regime_stats)
        best_time = best_key(time_stats)

        return {
            "symbol": symbol,
            "overall_win_rate": round(overall_win_rate, 4),
            "total_samples": len(signals),
            "best_regime": best_regime,
            "best_regime_ar": REGIME_AR.get(best_regime or "", best_regime),
            "best_time_of_day": best_time,
            "best_time_of_day_ar": TIME_AR.get(best_time or "", best_time),
        }

    async def get_top_patterns(self, symbol: str) -> list[dict[str, Any]]:
        cached = await cache_get(REDIS_TOP_PATTERNS_KEY.format(symbol=symbol))
        if cached:
            return cached
        async with AsyncSessionLocal() as session:
            await self._cache_top_patterns(session, symbol)
        return await cache_get(REDIS_TOP_PATTERNS_KEY.format(symbol=symbol)) or []

    async def get_memory_summary(self, symbol: str) -> dict[str, Any]:
        cached = await cache_get(REDIS_SUMMARY_KEY.format(symbol=symbol))
        if cached:
            return cached
        async with AsyncSessionLocal() as session:
            summary = await self._build_summary(session, symbol)
            await cache_set(REDIS_SUMMARY_KEY.format(symbol=symbol), summary, ttl=3600)
            return summary

    async def get_all_patterns(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for sym in ACTIVE_SYMBOLS:
            out[sym] = await self.get_top_patterns(sym)
        return out

    async def get_all_summaries(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for sym in ACTIVE_SYMBOLS:
            out[sym] = await self.get_memory_summary(sym)
        return out

    async def broadcast_patterns(self, symbol: str | None = None) -> None:
        symbols = [symbol] if symbol else ACTIVE_SYMBOLS
        patterns_payload: dict[str, list[dict[str, Any]]] = {}
        summary_payload: dict[str, dict[str, Any]] = {}
        for sym in symbols:
            patterns_payload[sym] = await self.get_top_patterns(sym)
            summary_payload[sym] = await self.get_memory_summary(sym)
        await broadcaster.broadcast_memory_patterns(
            {"patterns": patterns_payload, "summaries": summary_payload}
        )

    async def get_agent_accuracy(
        self, session: AsyncSession, symbol: str, regime: str, agent_id: str
    ) -> float:
        patterns = await self.get_top_patterns(symbol)
        for p in patterns:
            if p.get("regime") == regime:
                return float(p.get("win_rate", 0.5))
        return 0.5

    async def record_signal_outcome(
        self, session: AsyncSession, symbol: str
    ) -> int:
        """Recompute patterns after new WIN/LOSS outcomes and broadcast."""
        count = await self.update_from_signals(session, symbol)
        await self.broadcast_patterns(symbol)
        return count


memory_engine = MemoryEngine()
