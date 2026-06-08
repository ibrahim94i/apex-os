"""Trading journal — Telegram signals, follow-up, and analysis."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import logger
from app.models.journal import FollowUpStatus, JournalEntry
from app.schemas import TradingSignalSchema
from app.schemas.journal import (
    JournalAnalysisSchema,
    JournalEntryCreateSchema,
    JournalEntrySchema,
    JournalFollowUpSchema,
    JournalSignalReportSchema,
    JournalSnrAnalyticsSchema,
)
from app.services.memory_engine import time_of_day

TIME_AR = {
    "morning": "صباحاً",
    "afternoon": "ظهراً",
    "evening": "مساءً",
    "night": "ليلاً",
}

SOURCE_AR = {"system_signal": "إشارات النظام", "personal": "قراراتك الشخصية"}
EMOTION_AR = {"confident": "الثقة", "hesitant": "التردد", "fearful": "الخوف"}

FOLLOW_UP_AR = {
    FollowUpStatus.PENDING.value: "بانتظار ردك",
    FollowUpStatus.ENTERED.value: "دخلت",
    FollowUpStatus.LOST.value: "خسرت",
    FollowUpStatus.IGNORED.value: "تجاهلت",
}


def calc_pnl(direction: str, entry: float, exit_: float) -> tuple[float, float]:
    if direction == "LONG":
        pnl = exit_ - entry
    else:
        pnl = entry - exit_
    pnl_pct = (pnl / entry) * 100 if entry else 0.0
    return round(pnl, 4), round(pnl_pct, 4)


def _resolved_system_signals(entries: list[JournalEntry]) -> list[JournalEntry]:
    return [
        e
        for e in entries
        if e.source == "system_signal"
        and e.follow_up_status in (FollowUpStatus.ENTERED.value, FollowUpStatus.LOST.value)
    ]


def _win_rate(entries: list[JournalEntry]) -> tuple[float, int]:
    if not entries:
        return 0.0, 0
    wins = sum(1 for e in entries if e.result == "win")
    return round(wins / len(entries), 4), len(entries)


def build_snr_analytics(entries: list[JournalEntry]) -> JournalSnrAnalyticsSchema:
    resolved = _resolved_system_signals(entries)
    inside = [e for e in resolved if e.snr_state == "inside_zone"]
    outside = [e for e in resolved if e.snr_state != "inside_zone"]
    inside_wr, inside_n = _win_rate(inside)
    outside_wr, outside_n = _win_rate(outside)
    return JournalSnrAnalyticsSchema(
        inside_zone_win_rate=inside_wr,
        inside_zone_resolved=inside_n,
        outside_zone_win_rate=outside_wr,
        outside_zone_resolved=outside_n,
        generated_at=datetime.now(timezone.utc),
    )


class TradingJournalService:
    ANALYSIS_EVERY = 5

    async def record_telegram_signal(
        self,
        session: AsyncSession,
        signal: TradingSignalSchema,
    ) -> JournalEntrySchema:
        """Auto-log journal row when a signal is sent on Telegram."""
        entry = JournalEntry(
            symbol=signal.symbol,
            direction=signal.direction.value,
            entry_price=signal.entry_price,
            exit_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            source="system_signal",
            emotion="hesitant",
            result="pending",
            follow_up_status=FollowUpStatus.PENDING.value,
            signal_confidence=signal.confidence,
            snr_state=signal.snr_state,
            snr_penalty=signal.snr_penalty,
            notes=f"إشارة Telegram — ثقة {signal.confidence * 100:.1f}%",
            pnl=0.0,
            pnl_pct=0.0,
            closed_at=signal.timestamp,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        logger.info(
            "journal_signal_recorded",
            symbol=signal.symbol,
            direction=signal.direction.value,
            journal_id=entry.id,
        )
        return self._to_schema(entry)

    async def apply_follow_up(
        self,
        session: AsyncSession,
        entry_id: int,
        data: JournalFollowUpSchema,
    ) -> JournalEntrySchema:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            raise ValueError("journal_entry_not_found")
        if entry.follow_up_status != FollowUpStatus.PENDING.value:
            raise ValueError("journal_entry_already_resolved")

        if data.action == "ignored":
            entry.follow_up_status = FollowUpStatus.IGNORED.value
            entry.result = "neutral"
            entry.exit_price = entry.entry_price
            entry.pnl = 0.0
            entry.pnl_pct = 0.0
            entry.notes = (entry.notes or "") + " | تجاهل الإشارة"
        elif data.action == "lost":
            assert data.exit_price is not None
            entry.follow_up_status = FollowUpStatus.LOST.value
            entry.result = "loss"
            entry.exit_price = data.exit_price
            entry.pnl, entry.pnl_pct = calc_pnl(entry.direction, entry.entry_price, entry.exit_price)
            entry.notes = (entry.notes or "") + " | خسارة — سعر الإغلاق"
        else:
            assert data.exit_price is not None and data.result is not None
            entry.follow_up_status = FollowUpStatus.ENTERED.value
            entry.result = data.result
            entry.exit_price = data.exit_price
            entry.pnl, entry.pnl_pct = calc_pnl(entry.direction, entry.entry_price, entry.exit_price)
            entry.notes = (entry.notes or "") + f" | دخلت — {data.result}"

        entry.closed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(entry)
        return self._to_schema(entry)

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
            follow_up_status=FollowUpStatus.ENTERED.value,
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
            select(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(limit)
        )
        return [self._to_schema(e) for e in result.scalars().all()]

    async def get_signal_report(self, session: AsyncSession) -> JournalSignalReportSchema:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.source == "system_signal")
        )
        signals = list(result.scalars().all())
        entered = [e for e in signals if e.follow_up_status == FollowUpStatus.ENTERED.value]
        ignored = [e for e in signals if e.follow_up_status == FollowUpStatus.IGNORED.value]
        lost = [e for e in signals if e.follow_up_status == FollowUpStatus.LOST.value]
        pending = [e for e in signals if e.follow_up_status == FollowUpStatus.PENDING.value]

        resolved = entered + lost
        wins = sum(1 for e in resolved if e.result == "win")
        win_rate = wins / len(resolved) if resolved else 0.0

        total_profit = sum(e.pnl for e in resolved if e.pnl > 0)
        total_loss = sum(abs(e.pnl) for e in resolved if e.pnl < 0)
        net_pnl = sum(e.pnl for e in resolved)

        return JournalSignalReportSchema(
            total_signals=len(signals),
            entered_count=len(entered),
            ignored_count=len(ignored),
            lost_count=len(lost),
            pending_count=len(pending),
            win_rate=round(win_rate, 4),
            total_profit=round(total_profit, 4),
            total_loss=round(total_loss, 4),
            net_pnl=round(net_pnl, 4),
            generated_at=datetime.now(timezone.utc),
        )

    async def get_latest_analysis(
        self, session: AsyncSession
    ) -> JournalAnalysisSchema | None:
        count = await self._count_entries(session)
        signal_report = await self.get_signal_report(session)
        all_signals = await self._list_system_signals(session)
        snr_analytics = build_snr_analytics(all_signals)
        if count < self.ANALYSIS_EVERY and signal_report.total_signals == 0:
            if signal_report.total_signals > 0:
                return JournalAnalysisSchema(
                    total_trades=0,
                    win_rate=0.0,
                    best_time_of_day="morning",
                    best_time_of_day_ar="صباحاً",
                    system_losses=0,
                    personal_losses=0,
                    worse_source_ar="—",
                    fearful_losses=0,
                    confident_losses=0,
                    worse_emotion_ar="—",
                    recommendation_ar="سجّل متابعتك للإشارات باستخدام الأزرار أعلاه.",
                    generated_at=datetime.now(timezone.utc),
                    signal_report=signal_report,
                    snr_analytics=snr_analytics,
                )
            return None
        if count % self.ANALYSIS_EVERY != 0 and count < self.ANALYSIS_EVERY:
            base = await self._build_analysis(session, count)
            return base.model_copy(
                update={"signal_report": signal_report, "snr_analytics": snr_analytics}
            )
        base = await self._build_analysis(session, max(count, 1))
        return base.model_copy(
            update={"signal_report": signal_report, "snr_analytics": snr_analytics}
        )

    async def _maybe_analyze(
        self, session: AsyncSession
    ) -> JournalAnalysisSchema | None:
        count = await self._count_entries(session)
        signal_report = await self.get_signal_report(session)
        all_signals = await self._list_system_signals(session)
        snr_analytics = build_snr_analytics(all_signals)
        if count >= self.ANALYSIS_EVERY and count % self.ANALYSIS_EVERY == 0:
            base = await self._build_analysis(session, count)
            return base.model_copy(
                update={"signal_report": signal_report, "snr_analytics": snr_analytics}
            )
        if signal_report.total_signals > 0:
            return JournalAnalysisSchema(
                total_trades=count,
                win_rate=signal_report.win_rate,
                best_time_of_day="morning",
                best_time_of_day_ar="صباحاً",
                system_losses=signal_report.lost_count,
                personal_losses=0,
                worse_source_ar="—",
                fearful_losses=0,
                confident_losses=0,
                worse_emotion_ar="—",
                recommendation_ar="راجع تقرير الإشارات أعلاه.",
                generated_at=datetime.now(timezone.utc),
                signal_report=signal_report,
                snr_analytics=snr_analytics,
            )
        return None

    async def _list_system_signals(self, session: AsyncSession) -> list[JournalEntry]:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.source == "system_signal")
        )
        return list(result.scalars().all())

    async def _count_entries(self, session: AsyncSession) -> int:
        result = await session.execute(select(JournalEntry))
        return len(result.scalars().all())

    async def _build_analysis(
        self, session: AsyncSession, total: int
    ) -> JournalAnalysisSchema:
        result = await session.execute(
            select(JournalEntry)
            .where(JournalEntry.follow_up_status != FollowUpStatus.PENDING.value)
            .order_by(JournalEntry.closed_at.desc())
            .limit(total)
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
            signal_report=None,
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
            follow_up_status=entry.follow_up_status,
            signal_confidence=entry.signal_confidence,
            snr_state=entry.snr_state,
            snr_penalty=entry.snr_penalty,
            notes=entry.notes,
            pnl=entry.pnl,
            pnl_pct=entry.pnl_pct,
            closed_at=entry.closed_at,
            created_at=entry.created_at,
        )


trading_journal_service = TradingJournalService()
