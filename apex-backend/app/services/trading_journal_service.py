"""Trading journal — manual entries and periodic analysis."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import JournalEntry
from app.schemas.journal import JournalAnalysisSchema, JournalEntryCreateSchema, JournalEntrySchema
from app.services.memory_engine import time_of_day

TIME_AR = {
    "morning": "صباحاً",
    "afternoon": "ظهراً",
    "evening": "مساءً",
    "night": "ليلاً",
}

SOURCE_AR = {"system_signal": "إشارات النظام", "personal": "قراراتك الشخصية"}
EMOTION_AR = {"confident": "الثقة", "hesitant": "التردد", "fearful": "الخوف"}


def calc_pnl(direction: str, entry: float, exit_: float) -> tuple[float, float]:
    if direction == "LONG":
        pnl = exit_ - entry
    else:
        pnl = entry - exit_
    pnl_pct = (pnl / entry) * 100 if entry else 0.0
    return round(pnl, 4), round(pnl_pct, 4)


class TradingJournalService:
    ANALYSIS_EVERY = 5

    async def create_entry(
        self, session: AsyncSession, data: JournalEntryCreateSchema
    ) -> tuple[JournalEntrySchema, JournalAnalysisSchema | None]:
        pnl, pnl_pct = calc_pnl(data.direction, data.entry_price, data.exit_price)
        entry = JournalEntry(
            symbol=data.symbol,
            direction=data.direction,
            entry_price=data.entry_price,
            exit_price=data.exit_price,
            stop_loss=data.stop_loss,
            take_profit=data.take_profit,
            source=data.source,
            emotion=data.emotion,
            result=data.result,
            notes=data.notes,
            pnl=pnl,
            pnl_pct=pnl_pct,
            closed_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        analysis = await self._maybe_analyze(session)
        return self._to_schema(entry), analysis

    async def list_entries(
        self, session: AsyncSession, limit: int = 50
    ) -> list[JournalEntrySchema]:
        result = await session.execute(
            select(JournalEntry).order_by(JournalEntry.closed_at.desc()).limit(limit)
        )
        return [self._to_schema(e) for e in result.scalars().all()]

    async def get_latest_analysis(
        self, session: AsyncSession
    ) -> JournalAnalysisSchema | None:
        count = await self._count_entries(session)
        if count < self.ANALYSIS_EVERY:
            return None
        if count % self.ANALYSIS_EVERY != 0:
            return await self._build_analysis(session, count)
        return await self._build_analysis(session, count)

    async def _maybe_analyze(
        self, session: AsyncSession
    ) -> JournalAnalysisSchema | None:
        count = await self._count_entries(session)
        if count >= self.ANALYSIS_EVERY and count % self.ANALYSIS_EVERY == 0:
            return await self._build_analysis(session, count)
        return None

    async def _count_entries(self, session: AsyncSession) -> int:
        result = await session.execute(select(JournalEntry))
        return len(result.scalars().all())

    async def _build_analysis(
        self, session: AsyncSession, total: int
    ) -> JournalAnalysisSchema:
        result = await session.execute(
            select(JournalEntry).order_by(JournalEntry.closed_at.desc()).limit(total)
        )
        entries = list(result.scalars().all())
        wins = sum(1 for e in entries if e.result == "win")
        win_rate = wins / len(entries) if entries else 0.0

        time_stats: dict[str, dict[str, int]] = {}
        for e in entries:
            tod = time_of_day(e.closed_at.hour)
            if tod not in time_stats:
                time_stats[tod] = {"wins": 0, "total": 0}
            time_stats[tod]["total"] += 1
            if e.result == "win":
                time_stats[tod]["wins"] += 1

        best_time = max(
            time_stats,
            key=lambda k: time_stats[k]["wins"] / time_stats[k]["total"]
            if time_stats[k]["total"]
            else 0,
            default="morning",
        )

        system_losses = sum(
            1 for e in entries if e.result == "loss" and e.source == "system_signal"
        )
        personal_losses = sum(
            1 for e in entries if e.result == "loss" and e.source == "personal"
        )
        if system_losses > personal_losses:
            worse_source = "إشارات النظام"
        elif personal_losses > system_losses:
            worse_source = "قراراتك الشخصية"
        else:
            worse_source = "متساوٍ — راجع كلا النوعين"

        fearful_losses = sum(
            1 for e in entries if e.result == "loss" and e.emotion == "fearful"
        )
        confident_losses = sum(
            1 for e in entries if e.result == "loss" and e.emotion == "confident"
        )
        if fearful_losses > confident_losses:
            worse_emotion = "الخوف"
        elif confident_losses > fearful_losses:
            worse_emotion = "الثقة المفرطة"
        else:
            worse_emotion = "متساوٍ"

        recent_losses = sum(1 for e in entries[:5] if e.result == "loss")
        if win_rate >= 0.5 and recent_losses <= 2:
            recommendation = "استمر — أداؤك جيد. التزم بخطة إدارة المخاطر."
        elif recent_losses >= 3:
            recommendation = "توقف اليوم — 3 خسائر في آخر صفقاتك. استأنف غداً بذهنية صافية."
        else:
            recommendation = "كن حذراً — راجع الصفقات الخاسرة قبل فتح صفقة جديدة."

        return JournalAnalysisSchema(
            total_trades=len(entries),
            win_rate=round(win_rate, 4),
            best_time_of_day=best_time,
            best_time_of_day_ar=TIME_AR.get(best_time, best_time),
            system_losses=system_losses,
            personal_losses=personal_losses,
            worse_source_ar=worse_source,
            fearful_losses=fearful_losses,
            confident_losses=confident_losses,
            worse_emotion_ar=worse_emotion,
            recommendation_ar=recommendation,
            generated_at=datetime.now(timezone.utc),
        )

    def _to_schema(self, entry: JournalEntry) -> JournalEntrySchema:
        return JournalEntrySchema(
            id=entry.id,
            symbol=entry.symbol,
            direction=entry.direction,
            entry_price=entry.entry_price,
            exit_price=entry.exit_price,
            stop_loss=entry.stop_loss,
            take_profit=entry.take_profit,
            source=entry.source,
            emotion=entry.emotion,
            result=entry.result,
            notes=entry.notes,
            pnl=entry.pnl,
            pnl_pct=entry.pnl_pct,
            closed_at=entry.closed_at,
        )


trading_journal_service = TradingJournalService()
