"""Backtesting runner — evaluates signal outcomes from historical price data."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceBar, TradingSignal
from app.models.phase3 import SignalOutcome
from app.logging_config import logger


@dataclass
class RegimeStats:
    regime: str
    total: int = 0
    wins: int = 0
    losses: int = 0
    partials: int = 0
    win_rate: float = 0.0
    avg_rr: float = 0.0


@dataclass
class AgentStats:
    agent_id: str
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0


@dataclass
class BacktestResults:
    symbol: str
    total_signals: int = 0
    evaluated: int = 0
    wins: int = 0
    losses: int = 0
    partials: int = 0
    overall_win_rate: float = 0.0
    overall_avg_rr: float = 0.0
    by_regime: list[RegimeStats] = field(default_factory=list)
    by_agent: list[AgentStats] = field(default_factory=list)
    best_regime: str | None = None
    run_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Backtester:
    LOOKAHEAD_BARS = 60

    async def run(self, session: AsyncSession, symbol: str | None = None) -> BacktestResults:
        query = select(TradingSignal).where(
            TradingSignal.direction.in_(["LONG", "SHORT"])
        )
        if symbol:
            query = query.where(TradingSignal.symbol == symbol)
        query = query.order_by(TradingSignal.timestamp.asc())

        result = await session.execute(query)
        signals = result.scalars().all()

        results = BacktestResults(
            symbol=symbol or "ALL",
            total_signals=len(signals),
        )

        regime_map: dict[str, RegimeStats] = {}
        rr_values: list[float] = []

        for signal in signals:
            outcome, exit_price, rr = await self._evaluate_signal(session, signal)
            if outcome is None:
                continue

            signal.outcome = outcome
            signal.actual_exit_price = exit_price
            signal.rr_achieved = rr
            results.evaluated += 1
            rr_values.append(rr)

            regime_key = signal.regime.value if hasattr(signal.regime, "value") else str(signal.regime)
            if regime_key not in regime_map:
                regime_map[regime_key] = RegimeStats(regime=regime_key)
            stats = regime_map[regime_key]
            stats.total += 1
            stats.avg_rr = ((stats.avg_rr * (stats.total - 1)) + rr) / stats.total

            if outcome == SignalOutcome.WIN.value:
                results.wins += 1
                stats.wins += 1
            elif outcome == SignalOutcome.LOSS.value:
                results.losses += 1
                stats.losses += 1
            else:
                results.partials += 1
                stats.partials += 1

            stats.win_rate = stats.wins / stats.total if stats.total else 0.0

        for stats in regime_map.values():
            results.by_regime.append(stats)

        if results.evaluated:
            results.overall_win_rate = results.wins / results.evaluated
            results.overall_avg_rr = sum(rr_values) / len(rr_values)

        if results.by_regime:
            best = max(results.by_regime, key=lambda r: r.win_rate)
            results.best_regime = best.regime

        await session.commit()

        from app.services.memory_engine import memory_engine

        if symbol:
            await memory_engine.record_signal_outcome(session, symbol)
        else:
            for sym in {s.symbol for s in signals}:
                await memory_engine.record_signal_outcome(session, sym)

        logger.info(
            "backtest_complete",
            symbol=results.symbol,
            evaluated=results.evaluated,
            win_rate=results.overall_win_rate,
        )
        return results

    async def _evaluate_signal(
        self, session: AsyncSession, signal: TradingSignal
    ) -> tuple[str | None, float | None, float]:
        direction = signal.direction.value if hasattr(signal.direction, "value") else signal.direction

        bars_result = await session.execute(
            select(PriceBar)
            .where(
                and_(
                    PriceBar.symbol == signal.symbol,
                    PriceBar.timestamp > signal.timestamp,
                )
            )
            .order_by(PriceBar.timestamp.asc())
            .limit(self.LOOKAHEAD_BARS)
        )
        bars = bars_result.scalars().all()
        if not bars:
            return None, None, 0.0

        entry = signal.entry_price
        sl = signal.stop_loss
        tp = signal.take_profit
        risk = abs(entry - sl)
        if risk == 0:
            return SignalOutcome.PARTIAL.value, bars[-1].close, 0.0

        hit_tp = False
        hit_sl = False
        exit_price = bars[-1].close
        exit_bar_idx = len(bars) - 1
        max_adverse = 0.0

        for i, bar in enumerate(bars):
            if direction == "LONG":
                adverse = max(0.0, entry - bar.low)
                max_adverse = max(max_adverse, adverse)
                if bar.low <= sl:
                    hit_sl = True
                    exit_price = sl
                    exit_bar_idx = i
                    break
                if bar.high >= tp:
                    hit_tp = True
                    exit_price = tp
                    exit_bar_idx = i
                    break
            elif direction == "SHORT":
                adverse = max(0.0, bar.high - entry)
                max_adverse = max(max_adverse, adverse)
                if bar.high >= sl:
                    hit_sl = True
                    exit_price = sl
                    exit_bar_idx = i
                    break
                if bar.low <= tp:
                    hit_tp = True
                    exit_price = tp
                    exit_bar_idx = i
                    break

        max_dd_pct = (max_adverse / risk * 100) if risk > 0 else 0.0
        time_hours = round((exit_bar_idx + 1), 2)  # H1 bars ≈ hours

        if hit_tp:
            outcome = SignalOutcome.WIN.value
            rr = abs(tp - entry) / risk
            pnl = signal.position_size * abs(tp - entry)
        elif hit_sl:
            outcome = SignalOutcome.LOSS.value
            rr = -1.0
            pnl = -signal.position_size * risk
        else:
            outcome = SignalOutcome.PARTIAL.value
            if direction == "LONG":
                rr = (exit_price - entry) / risk
                pnl = signal.position_size * (exit_price - entry)
            else:
                rr = (entry - exit_price) / risk
                pnl = signal.position_size * (entry - exit_price)

        signal.max_drawdown_during_trade = round(max_dd_pct, 4)
        signal.time_in_trade_hours = time_hours
        signal.profit_loss_amount = round(pnl, 4)

        return outcome, exit_price, round(rr, 4)

    async def evaluate_pending_signals(
        self, session: AsyncSession, symbol: str
    ) -> int:
        """Evaluate open signals and refresh memory when WIN/LOSS is determined."""
        result = await session.execute(
            select(TradingSignal).where(
                TradingSignal.symbol == symbol,
                TradingSignal.outcome.is_(None),
                TradingSignal.direction.in_(["LONG", "SHORT"]),
            )
        )
        pending = result.scalars().all()
        resolved = 0
        for signal in pending:
            outcome, exit_price, rr = await self._evaluate_signal(session, signal)
            if outcome is None:
                continue
            signal.outcome = outcome
            signal.actual_exit_price = exit_price
            signal.rr_achieved = rr
            if outcome in ("WIN", "LOSS"):
                resolved += 1

        if resolved:
            await session.commit()
            from app.services.memory_engine import memory_engine

            await memory_engine.record_signal_outcome(session, symbol)
        return resolved


backtester = Backtester()
