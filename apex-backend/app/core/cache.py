"""Redis caching utilities."""

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.core.redis_client import (
    CacheKeys,
    cache_get,
    cache_get_list,
    cache_push_list,
    cache_set,
)


async def set_latest_price(symbol: str, price: float, timestamp: str) -> None:
    await cache_set(
        CacheKeys.LATEST_PRICE.format(symbol=symbol),
        {"price": price, "timestamp": timestamp},
        ttl=1800,
    )


async def get_latest_price(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.LATEST_PRICE.format(symbol=symbol))


async def set_display_price(
    symbol: str,
    price: float,
    timestamp: str,
    *,
    source: str,
) -> None:
    """Dashboard-only live ticker — never used by agents, signals, or TwelveData pipeline."""
    await cache_set(
        CacheKeys.DISPLAY_PRICE.format(symbol=symbol),
        {"price": price, "timestamp": timestamp, "source": source},
        ttl=300,
    )


async def get_display_price(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.DISPLAY_PRICE.format(symbol=symbol))


async def set_latest_indicators(symbol: str, data: dict[str, Any]) -> None:
    await cache_set(CacheKeys.LATEST_INDICATORS.format(symbol=symbol), data, ttl=1800)


async def get_latest_indicators(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.LATEST_INDICATORS.format(symbol=symbol))


async def set_latest_regime(symbol: str, data: dict[str, Any]) -> None:
    await cache_set(CacheKeys.LATEST_REGIME.format(symbol=symbol), data, ttl=1800)


async def get_latest_regime(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.LATEST_REGIME.format(symbol=symbol))


async def set_latest_signal(symbol: str, data: dict[str, Any]) -> None:
    await cache_set(CacheKeys.LATEST_SIGNAL.format(symbol=symbol), data, ttl=3600)
    await cache_push_list(CacheKeys.SIGNAL_HISTORY.format(symbol=symbol), data, max_len=20)


async def get_latest_signal(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.LATEST_SIGNAL.format(symbol=symbol))


async def get_signal_history(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    items = await cache_get_list(CacheKeys.SIGNAL_HISTORY.format(symbol=symbol), 0, limit - 1)
    return items


async def set_kill_switch_status(data: dict[str, Any]) -> None:
    await cache_set(CacheKeys.KILL_SWITCH, data)


async def get_kill_switch_status() -> dict[str, Any] | None:
    return await cache_get(CacheKeys.KILL_SWITCH)


async def set_feed_last_update(
    source: str,
    bar_timestamp: str,
    *,
    received_at: str | None = None,
) -> None:
    """Record feed activity. `received_at` is used for staleness; bar_timestamp is the candle time."""
    now = received_at or datetime.now(timezone.utc).isoformat()
    await cache_set(
        CacheKeys.FEED_LAST_UPDATE.format(source=source),
        {"timestamp": bar_timestamp, "received_at": now},
        ttl=7200,
    )


async def get_feed_last_update(source: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.FEED_LAST_UPDATE.format(source=source))


async def set_dashboard_state(symbol: str, data: dict[str, Any]) -> None:
    await cache_set(CacheKeys.DASHBOARD_STATE.format(symbol=symbol), data, ttl=60)


async def get_dashboard_state(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.DASHBOARD_STATE.format(symbol=symbol))


async def set_agent_consensus(symbol: str, data: dict[str, Any]) -> None:
    await cache_set(
        CacheKeys.AGENT_CONSENSUS.format(symbol=symbol),
        data,
        ttl=settings.agent_consensus_ttl_seconds,
    )


async def get_agent_consensus(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.AGENT_CONSENSUS.format(symbol=symbol))


async def set_agent_consensus_last_good(symbol: str, data: dict[str, Any]) -> None:
    await cache_set(
        CacheKeys.AGENT_CONSENSUS_LAST_GOOD.format(symbol=symbol),
        data,
        ttl=settings.agent_consensus_last_good_ttl_seconds,
    )


async def get_agent_consensus_last_good(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.AGENT_CONSENSUS_LAST_GOOD.format(symbol=symbol))


async def set_hourly_report(data: dict[str, Any]) -> None:
    await cache_set(CacheKeys.HOURLY_REPORT, data, ttl=7200)


async def get_hourly_report() -> dict[str, Any] | None:
    return await cache_get(CacheKeys.HOURLY_REPORT)


async def set_latest_snr(symbol: str, data: dict[str, Any]) -> None:
    await cache_set(CacheKeys.LATEST_SNR.format(symbol=symbol), data, ttl=1800)


async def get_latest_snr(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.LATEST_SNR.format(symbol=symbol))


async def set_news_verdict(symbol: str, data: dict[str, Any]) -> None:
    await cache_set(
        CacheKeys.NEWS_VERDICT.format(symbol=symbol),
        data,
        ttl=settings.news_verdict_ttl_seconds,
    )


async def get_news_verdict(symbol: str) -> dict[str, Any] | None:
    return await cache_get(CacheKeys.NEWS_VERDICT.format(symbol=symbol))
