"""REST API route handlers."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    get_agent_consensus,
    get_dashboard_state,
    get_kill_switch_status,
    get_latest_price,
    get_latest_regime,
    get_latest_signal,
    get_signal_history,
    set_dashboard_state,
)
from app.core.redis_client import redis_health_check
from app.database import get_db
from app.engines.kill_switch import kill_switch
from app.models import RegimeSnapshot, TradingSignal
from app.schemas import (
    AgentConsensus,
    AgentVerdict,
    DashboardStateSchema,
    HealthResponse,
    KillSwitchStatus,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
    TradingSignalSchema,
)

router = APIRouter()


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """Lightweight liveness probe — no DB/Redis required (for Railway healthcheck)."""
    return {"status": "alive"}


@router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_db)) -> HealthResponse:
    db_status = "ok"
    try:
        await session.execute(select(1))
    except Exception:
        db_status = "error"

    redis_status = "ok" if await redis_health_check() else "error"

    from app.config import settings

    return HealthResponse(
        status="ok" if db_status == "ok" and redis_status == "ok" else "degraded",
        environment=settings.environment,
        database=db_status,
        redis=redis_status,
    )


@router.get("/dashboard", response_model=DashboardStateSchema)
async def get_dashboard(symbol: str = "XAUUSD") -> DashboardStateSchema:
    cached = await get_dashboard_state(symbol)
    if cached and cached.get("symbol") == symbol:
        return DashboardStateSchema(**cached)

    regime_data = await get_latest_regime(symbol)
    signal_data = await get_latest_signal(symbol)
    kill_data = await get_kill_switch_status()
    history = await get_signal_history(symbol, 20)
    price_data = await get_latest_price(symbol)

    regime = RegimeSnapshotSchema(**regime_data) if regime_data else None
    latest_signal = TradingSignalSchema(**signal_data) if signal_data else None
    kill = (
        KillSwitchStatusSchema(**kill_data)
        if kill_data
        else KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE)
    )
    consensus_data = await get_agent_consensus(symbol)

    state = DashboardStateSchema(
        regime=regime,
        latest_signal=latest_signal,
        kill_switch=kill,
        signal_history=[TradingSignalSchema(**s) for s in history],
        current_price=price_data["price"] if price_data else None,
        symbol=symbol,
        agent_consensus=AgentConsensus(**consensus_data) if consensus_data else None,
    )

    await set_dashboard_state(symbol, state.model_dump(mode="json"))
    return state


@router.get("/signals/latest", response_model=TradingSignalSchema | None)
async def get_latest_trading_signal(symbol: str = "BTCUSDT") -> TradingSignalSchema | None:
    data = await get_latest_signal(symbol)
    if not data:
        result = None
    else:
        result = TradingSignalSchema(**data)
    return result


@router.get("/signals/history", response_model=list[TradingSignalSchema])
async def get_signals_history(symbol: str = "BTCUSDT", limit: int = 20) -> list[TradingSignalSchema]:
    history = await get_signal_history(symbol, limit)
    return [TradingSignalSchema(**s) for s in history]


@router.get("/regime/current", response_model=RegimeSnapshotSchema | None)
async def get_current_regime(symbol: str = "BTCUSDT") -> RegimeSnapshotSchema | None:
    data = await get_latest_regime(symbol)
    if not data:
        return None
    return RegimeSnapshotSchema(**data)


@router.get("/kill-switch", response_model=KillSwitchStatusSchema)
async def get_kill_switch_status_endpoint(
    session: AsyncSession = Depends(get_db),
) -> KillSwitchStatusSchema:
    await kill_switch.load_from_cache()
    return await kill_switch.evaluate(session)


@router.get("/signals/db", response_model=list[TradingSignalSchema])
async def get_signals_from_db(
    symbol: str = "BTCUSDT",
    limit: int = 20,
    session: AsyncSession = Depends(get_db),
) -> list[TradingSignalSchema]:
    result = await session.execute(
        select(TradingSignal)
        .where(TradingSignal.symbol == symbol)
        .order_by(desc(TradingSignal.timestamp))
        .limit(limit)
    )
    signals = result.scalars().all()
    return [
        TradingSignalSchema(
            id=s.id,
            symbol=s.symbol,
            timestamp=s.timestamp,
            direction=s.direction.value,
            confidence=s.confidence,
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            take_profit=s.take_profit,
            position_size=s.position_size,
            regime=s.regime.value,
            degraded=s.degraded,
            degradation_reason=s.degradation_reason,
            kill_switch_active=s.kill_switch_active,
            snr_state=s.snr_state,
            snr_penalty=s.snr_penalty,
        )
        for s in signals
    ]


@router.get("/regime/db", response_model=list[RegimeSnapshotSchema])
async def get_regime_from_db(
    symbol: str = "BTCUSDT",
    limit: int = 10,
    session: AsyncSession = Depends(get_db),
) -> list[RegimeSnapshotSchema]:
    result = await session.execute(
        select(RegimeSnapshot)
        .where(RegimeSnapshot.symbol == symbol)
        .order_by(desc(RegimeSnapshot.timestamp))
        .limit(limit)
    )
    regimes = result.scalars().all()
    return [
        RegimeSnapshotSchema(
            symbol=r.symbol,
            timestamp=r.timestamp,
            regime=r.regime.value,
            confidence=r.confidence,
            adx_value=r.adx_value,
            volatility_pct=r.volatility_pct,
            trend_strength=r.trend_strength,
        )
        for r in regimes
    ]


@router.get("/market/bars")
async def get_market_bars(symbol: str = "XAUUSD", limit: int = 200) -> dict:
    from app.config.assets import ACTIVE_SYMBOLS
    from app.services.market_data_store import fetch_bars_from_db
    from app.services.pipeline import compute_snr_for_symbol

    if symbol not in ACTIVE_SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not active")
    bars = await fetch_bars_from_db(symbol, min(limit, 500))
    snr = await compute_snr_for_symbol(symbol)
    return {
        "symbol": symbol,
        "bars": bars,
        "snr": snr.model_dump(mode="json") if snr else None,
    }


@router.get("/market/snr")
async def get_market_snr(symbol: str = "XAUUSD") -> dict:
    from app.config.assets import ACTIVE_SYMBOLS
    from app.core.cache import get_latest_snr
    from app.services.pipeline import compute_snr_for_symbol

    if symbol not in ACTIVE_SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not active")
    cached = await get_latest_snr(symbol)
    if cached:
        return cached
    snr = await compute_snr_for_symbol(symbol)
    if not snr:
        raise HTTPException(status_code=404, detail="SNR data unavailable")
    return snr.model_dump(mode="json")


@router.get("/price/current")
async def get_current_price(symbol: str = "XAUUSD") -> dict:
    data = await get_latest_price(symbol)
    if not data:
        raise HTTPException(status_code=404, detail="No price data available")
    return data


@router.get("/agents/consensus", response_model=AgentConsensus | None)
async def get_agents_consensus(symbol: str = "BTCUSDT") -> AgentConsensus | None:
    data = await get_agent_consensus(symbol)
    if not data:
        return None
    return AgentConsensus(**data)


@router.get("/agents/verdicts", response_model=list[AgentVerdict])
async def get_agent_verdicts(symbol: str = "BTCUSDT") -> list[AgentVerdict]:
    data = await get_agent_consensus(symbol)
    if not data:
        return []
    consensus = AgentConsensus(**data)
    return consensus.verdicts


@router.get("/feeds/status")
async def get_feeds_status() -> dict:
    from app.feeds.twelvedata_limiter import get_credit_usage_report
    from app.services.feed_health_service import check_feed_health
    from app.config.assets import ACTIVE_SYMBOLS
    from app.feeds.manager import feed_manager

    health = [await check_feed_health(sym) for sym in ACTIVE_SYMBOLS]
    return {
        "manager": feed_manager.get_status(),
        "twelvedata_credits": await get_credit_usage_report(),
        "health": [
            {
                "symbol": h.symbol,
                "feed_type": h.feed_type,
                "market_open": h.market_open,
                "feed_running": h.feed_running,
                "stale": h.stale,
                "age_seconds": h.age_seconds,
                "last_update": h.last_update.isoformat() if h.last_update else None,
            }
            for h in health
        ],
    }


@router.post("/feeds/restart")
async def restart_feeds(symbol: str | None = None, force: bool = False) -> dict:
    """Restart feeds without rebooting the whole system."""
    from app.services.feed_health_service import recover_feed, run_recovery_cycle
    from app.feeds.manager import feed_manager

    if symbol:
        ok = await recover_feed(symbol, "manual_restart")
        return {"symbol": symbol, "recovered": ok, "status": feed_manager.get_status()}

    report = await run_recovery_cycle(force=force)
    return {
        "actions": report.actions,
        "feeds": [
            {
                "symbol": f.symbol,
                "recovered": f.recovered,
                "stale": f.stale,
                "feed_running": f.feed_running,
            }
            for f in report.feeds
        ],
    }
