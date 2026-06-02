"""Backtest, memory, and multi-asset API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.assets import ACTIVE_SYMBOLS
from app.core.cache import get_hourly_report
from app.database import get_db
from app.engines.kill_switch import kill_switch
from app.schemas import DashboardStateSchema, KillSwitchStatusSchema
from app.schemas.account import AccountModeSchema
from app.schemas.market import HourlyReportSchema, MarketStatusSchema
from app.schemas.phase3 import (
    BacktestResultsSchema,
    ConfidenceBucketSchema,
    FeedStatusSchema,
    MemoryPatternSchema,
    MemorySummarySchema,
    MultiAssetDashboardSchema,
    PerformanceSummarySchema,
    RegimeBacktestStats,
    RegimePerformanceSchema,
)
from app.services.performance_engine import performance_engine
from app.services.backtester import backtester
from app.services.dashboard_builder import build_asset_dashboard_state
from app.services.feed_health_service import build_feed_status_payload
from app.services.hourly_report_service import build_hourly_report
from app.services.market_status_service import build_all_market_statuses
from app.services.account_service import account_service
from app.services.memory_engine import memory_engine

phase3_router = APIRouter()


def _performance_to_schema(summary) -> PerformanceSummarySchema:
    return PerformanceSummarySchema(
        total_signals=summary.total_signals,
        evaluated_signals=summary.evaluated_signals,
        overall_win_rate=summary.overall_win_rate,
        daily_win_rate=summary.daily_win_rate,
        profit_factor=summary.profit_factor,
        expectancy_per_trade=summary.expectancy_per_trade,
        max_drawdown_pct=summary.max_drawdown_pct,
        best_regime=summary.best_regime,
        best_regime_ar=summary.best_regime_ar,
        worst_regime=summary.worst_regime,
        worst_regime_ar=summary.worst_regime_ar,
        by_regime=[
            RegimePerformanceSchema(
                regime=r.regime,
                regime_ar=r.regime_ar,
                total=r.total,
                wins=r.wins,
                losses=r.losses,
                win_rate=r.win_rate,
                profit_factor=r.profit_factor,
                expectancy=r.expectancy,
            )
            for r in summary.by_regime
        ],
        confidence_vs_accuracy=[
            ConfidenceBucketSchema(
                bucket=c.bucket,
                total=c.total,
                wins=c.wins,
                accuracy=c.accuracy,
            )
            for c in summary.confidence_vs_accuracy
        ],
        calibration_status=summary.calibration_status,
        calibration_status_ar=summary.calibration_status_ar,
        calibration_color=summary.calibration_color,
        run_at=summary.run_at,
    )


@phase3_router.get("/performance/summary", response_model=PerformanceSummarySchema)
async def get_performance_summary(
    symbol: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> PerformanceSummarySchema:
    summary = await performance_engine.compute(session, symbol)
    return _performance_to_schema(summary)


@phase3_router.get("/backtest/run", response_model=BacktestResultsSchema)
async def run_backtest(
    symbol: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> BacktestResultsSchema:
    results = await backtester.run(session, symbol)
    await memory_engine.update_from_signals(session, symbol)
    return BacktestResultsSchema(
        symbol=results.symbol,
        total_signals=results.total_signals,
        evaluated=results.evaluated,
        wins=results.wins,
        losses=results.losses,
        partials=results.partials,
        overall_win_rate=results.overall_win_rate,
        overall_avg_rr=results.overall_avg_rr,
        by_regime=[
            RegimeBacktestStats(
                regime=r.regime,
                total=r.total,
                wins=r.wins,
                losses=r.losses,
                partials=r.partials,
                win_rate=r.win_rate,
                avg_rr=r.avg_rr,
            )
            for r in results.by_regime
        ],
        best_regime=results.best_regime,
        run_at=results.run_at,
    )


@phase3_router.get("/backtest/results", response_model=BacktestResultsSchema)
async def get_backtest_results(
    symbol: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> BacktestResultsSchema:
    return await run_backtest(symbol=symbol, session=session)


@phase3_router.get("/backtest/by-regime", response_model=list[RegimeBacktestStats])
async def get_backtest_by_regime(
    symbol: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[RegimeBacktestStats]:
    results = await backtester.run(session, symbol)
    return [
        RegimeBacktestStats(
            regime=r.regime,
            total=r.total,
            wins=r.wins,
            losses=r.losses,
            partials=r.partials,
            win_rate=r.win_rate,
            avg_rr=r.avg_rr,
        )
        for r in results.by_regime
    ]


@phase3_router.get("/memory/patterns", response_model=dict[str, list[MemoryPatternSchema]])
async def get_memory_patterns(
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[MemoryPatternSchema]]:
    out: dict[str, list[MemoryPatternSchema]] = {}
    for sym in ACTIVE_SYMBOLS:
        patterns = await memory_engine.get_top_patterns(sym)
        if not patterns:
            await memory_engine.update_from_signals(session, sym)
            patterns = await memory_engine.get_top_patterns(sym)
        out[sym] = [MemoryPatternSchema(**p) for p in patterns]
    return out


@phase3_router.get("/dashboard/multi", response_model=MultiAssetDashboardSchema)
async def get_multi_dashboard(
    session: AsyncSession = Depends(get_db),
) -> MultiAssetDashboardSchema:
    assets: dict[str, DashboardStateSchema] = {}
    memory: dict[str, list[MemoryPatternSchema]] = {}
    summaries: dict[str, MemorySummarySchema] = {}

    for sym in ACTIVE_SYMBOLS:
        assets[sym] = await build_asset_dashboard_state(sym)
        patterns = await memory_engine.get_top_patterns(sym)
        memory[sym] = [MemoryPatternSchema(**p) for p in patterns]
        summary = await memory_engine.get_memory_summary(sym)
        summaries[sym] = MemorySummarySchema(**summary)

    await kill_switch.load_from_cache()
    ks = await kill_switch.evaluate(session)

    market_status = await build_all_market_statuses()
    report_data = await get_hourly_report()
    hourly_report = (
        HourlyReportSchema(**report_data)
        if report_data
        else await build_hourly_report()
    )

    account_status = await account_service.get_status()
    feed_raw = await build_feed_status_payload()
    feed_status = {
        sym: FeedStatusSchema(**data) for sym, data in feed_raw.items()
    }

    return MultiAssetDashboardSchema(
        assets=assets,
        kill_switch=KillSwitchStatusSchema(**ks.model_dump()),
        memory_patterns=memory,
        memory_summaries=summaries,
        account=AccountModeSchema(**account_status),
        market_status=market_status,
        feed_status=feed_status,
        hourly_report=hourly_report,
    )
