"""Auto Calibration — performance metrics and GO LIVE evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import TradingSignal
from app.models.phase3 import SignalOutcome

REGIME_AR = {
    "TRENDING_UP": "اتجاه صاعد",
    "TRENDING_DOWN": "اتجاه هابط",
    "RANGING": "نطاق جانبي",
    "VOLATILE": "تذبذب عالي",
    "UNKNOWN": "غير محدد",
}


@dataclass
class RegimePerformance:
    regime: str
    regime_ar: str
    total: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0


@dataclass
class ConfidenceBucket:
    bucket: str
    total: int = 0
    wins: int = 0
    accuracy: float = 0.0


@dataclass
class PerformanceSummary:
    total_signals: int = 0
    evaluated_signals: int = 0
    overall_win_rate: float = 0.0
    daily_win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy_per_trade: float = 0.0
    max_drawdown_pct: float = 0.0
    best_regime: str | None = None
    best_regime_ar: str | None = None
    worst_regime: str | None = None
    worst_regime_ar: str | None = None
    by_regime: list[RegimePerformance] = field(default_factory=list)
    confidence_vs_accuracy: list[ConfidenceBucket] = field(default_factory=list)
    calibration_status: str = "PENDING"
    calibration_status_ar: str = "بانتظار 30 إشارة"
    calibration_color: str = "yellow"
    run_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PerformanceEngine:
    async def compute(self, session: AsyncSession, symbol: str | None = None) -> PerformanceSummary:
        query = select(TradingSignal).where(
            TradingSignal.direction.in_(["LONG", "SHORT"]),
            TradingSignal.outcome.isnot(None),
        )
        if symbol:
            query = query.where(TradingSignal.symbol == symbol)
        query = query.order_by(TradingSignal.timestamp.asc())

        result = await session.execute(query)
        signals = result.scalars().all()

        summary = PerformanceSummary(
            total_signals=await self._count_total(session, symbol),
            evaluated_signals=len(signals),
        )

        if not signals:
            return summary

        wins = [s for s in signals if s.outcome == SignalOutcome.WIN.value]
        losses = [s for s in signals if s.outcome == SignalOutcome.LOSS.value]
        summary.overall_win_rate = len(wins) / len(signals) if signals else 0.0

        today = datetime.now(timezone.utc).date()
        daily = [s for s in signals if s.timestamp.date() == today]
        daily_wins = [s for s in daily if s.outcome == SignalOutcome.WIN.value]
        summary.daily_win_rate = len(daily_wins) / len(daily) if daily else summary.overall_win_rate

        gross_profit = sum(s.profit_loss_amount or 0 for s in wins if (s.profit_loss_amount or 0) > 0)
        gross_loss = abs(sum(s.profit_loss_amount or 0 for s in losses if (s.profit_loss_amount or 0) < 0))
        if gross_loss > 0:
            summary.profit_factor = round(gross_profit / gross_loss, 4)
        elif gross_profit > 0:
            summary.profit_factor = 999.0

        pnl_values = [s.profit_loss_amount or 0 for s in signals if s.profit_loss_amount is not None]
        if pnl_values:
            summary.expectancy_per_trade = round(sum(pnl_values) / len(pnl_values), 4)

        summary.max_drawdown_pct = self._max_drawdown_pct(signals)
        summary.by_regime = self._regime_breakdown(signals)
        summary.confidence_vs_accuracy = self._confidence_buckets(signals)

        if summary.by_regime:
            best = max(summary.by_regime, key=lambda r: r.win_rate if r.total >= 3 else -1)
            worst = min(summary.by_regime, key=lambda r: r.win_rate if r.total >= 3 else 2)
            if best.total >= 3:
                summary.best_regime = best.regime
                summary.best_regime_ar = best.regime_ar
            if worst.total >= 3:
                summary.worst_regime = worst.regime
                summary.worst_regime_ar = worst.regime_ar

        self._apply_calibration_status(summary)
        return summary

    async def _count_total(self, session: AsyncSession, symbol: str | None) -> int:
        q = select(func.count()).select_from(TradingSignal).where(
            TradingSignal.direction.in_(["LONG", "SHORT"])
        )
        if symbol:
            q = q.where(TradingSignal.symbol == symbol)
        r = await session.execute(q)
        return int(r.scalar() or 0)

    def _max_drawdown_pct(self, signals: list[TradingSignal]) -> float:
        peak = 0.0
        equity = 0.0
        max_dd = 0.0
        for s in signals:
            pnl = s.profit_loss_amount or 0
            equity += pnl
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = ((peak - equity) / peak) * 100
                max_dd = max(max_dd, dd)
            intra = s.max_drawdown_during_trade or 0
            max_dd = max(max_dd, intra)
        return round(max_dd, 4)

    def _regime_breakdown(self, signals: list[TradingSignal]) -> list[RegimePerformance]:
        buckets: dict[str, list[TradingSignal]] = {}
        for s in signals:
            key = s.regime.value if hasattr(s.regime, "value") else str(s.regime)
            buckets.setdefault(key, []).append(s)

        out: list[RegimePerformance] = []
        for regime, group in buckets.items():
            wins = [g for g in group if g.outcome == SignalOutcome.WIN.value]
            losses = [g for g in group if g.outcome == SignalOutcome.LOSS.value]
            gp = sum(g.profit_loss_amount or 0 for g in wins if (g.profit_loss_amount or 0) > 0)
            gl = abs(sum(g.profit_loss_amount or 0 for g in losses if (g.profit_loss_amount or 0) < 0))
            pf = round(gp / gl, 4) if gl > 0 else (999.0 if gp > 0 else 0.0)
            pnls = [g.profit_loss_amount or 0 for g in group]
            exp = round(sum(pnls) / len(pnls), 4) if pnls else 0.0
            out.append(
                RegimePerformance(
                    regime=regime,
                    regime_ar=REGIME_AR.get(regime, regime),
                    total=len(group),
                    wins=len(wins),
                    losses=len(losses),
                    win_rate=len(wins) / len(group) if group else 0.0,
                    profit_factor=pf,
                    expectancy=exp,
                )
            )
        return out

    def _confidence_buckets(self, signals: list[TradingSignal]) -> list[ConfidenceBucket]:
        buckets = {
            "70-79%": (0.70, 0.80),
            "80-89%": (0.80, 0.90),
            "90-100%": (0.90, 1.01),
        }
        out: list[ConfidenceBucket] = []
        for label, (lo, hi) in buckets.items():
            group = [s for s in signals if lo <= s.confidence < hi]
            if not group:
                continue
            wins = sum(1 for s in group if s.outcome == SignalOutcome.WIN.value)
            out.append(
                ConfidenceBucket(
                    bucket=label,
                    total=len(group),
                    wins=wins,
                    accuracy=wins / len(group),
                )
            )
        return out

    def _apply_calibration_status(self, summary: PerformanceSummary) -> None:
        min_sig = settings.calibration_min_signals
        if summary.evaluated_signals < min_sig:
            summary.calibration_status = "PENDING"
            summary.calibration_status_ar = f"بانتظار {min_sig - summary.evaluated_signals} إشارة"
            summary.calibration_color = "yellow"
            return

        pf = summary.profit_factor
        exp = summary.expectancy_per_trade
        if pf > 1.5 and exp > 0:
            summary.calibration_status = "GO_LIVE"
            summary.calibration_status_ar = "جاهز للتداول الحي"
            summary.calibration_color = "green"
        elif pf >= 1.0:
            summary.calibration_status = "ADJUST"
            summary.calibration_status_ar = "يحتاج ضبط"
            summary.calibration_color = "yellow"
        else:
            summary.calibration_status = "NO_TRADE"
            summary.calibration_status_ar = "لا تداول"
            summary.calibration_color = "red"


performance_engine = PerformanceEngine()
