"""Builds MarketSnapshot from live pipeline context."""

from datetime import datetime, timezone

from app.config import settings
from app.core.cache import get_feed_last_update
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatusSchema, RegimeSnapshotSchema
from app.schemas.agent import MarketSnapshot
from app.services.account_service import account_service
from app.services.memory_engine import memory_engine


async def build_market_snapshot(
    symbol: str,
    price: float,
    indicators: IndicatorSnapshotSchema,
    regime: RegimeSnapshotSchema,
    kill_switch: KillSwitchStatusSchema,
) -> MarketSnapshot:
    feed_stale = await _is_feed_stale(symbol)
    patterns = await memory_engine.get_top_patterns(symbol)

    balance = await account_service.get_balance()

    return MarketSnapshot(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        price=price,
        indicators=indicators,
        regime=regime,
        kill_switch=kill_switch,
        account_balance=balance,
        max_risk_pct=settings.max_risk_per_trade_pct,
        max_drawdown_pct=settings.max_drawdown_pct,
        daily_loss_pct=kill_switch.daily_loss_pct or 0.0,
        consecutive_losses=kill_switch.consecutive_losses or 0,
        feed_stale=feed_stale,
        memory_patterns=patterns,
    )


async def _is_feed_stale(symbol: str) -> bool:
    now = datetime.now(timezone.utc)
    try:
        last = await get_feed_last_update(symbol)
    except Exception:
        return True
    if not last:
        return True
    ts = datetime.fromisoformat(last["timestamp"])
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (now - ts).total_seconds()
    return age > settings.feed_staleness_limit_seconds
