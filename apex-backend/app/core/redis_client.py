import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings
from app.logging_config import logger

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def redis_health_check() -> bool:
    try:
        client = await get_redis()
        return await client.ping()
    except Exception as exc:
        logger.error("redis_health_check_failed", error=str(exc))
        return False


class CacheKeys:
    LATEST_PRICE = "apex:latest_price:{symbol}"
    LATEST_INDICATORS = "apex:indicators:{symbol}"
    LATEST_REGIME = "apex:regime:{symbol}"
    LATEST_SIGNAL = "apex:signal:{symbol}"
    KILL_SWITCH = "apex:kill_switch"
    SIGNAL_HISTORY = "apex:signal_history:{symbol}"
    FEED_LAST_UPDATE = "apex:feed_last_update:{source}"
    DASHBOARD_STATE = "apex:dashboard_state:{symbol}"
    AGENT_CONSENSUS = "apex:agent_consensus:{symbol}"
    AGENT_CONSENSUS_LAST_GOOD = "apex:agent_consensus_last_good:{symbol}"
    NEWS_VERDICT = "apex:news_verdict:{symbol}"
    HOURLY_REPORT = "apex:hourly_report"
    LATEST_SNR = "apex:snr:{symbol}"
    DISPLAY_PRICE = "apex:display_price:{symbol}"


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    client = await get_redis()
    serialized = json.dumps(value, default=str)
    if ttl:
        await client.setex(key, ttl, serialized)
    else:
        await client.set(key, serialized)


async def cache_get(key: str) -> Any | None:
    client = await get_redis()
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_delete(key: str) -> None:
    client = await get_redis()
    await client.delete(key)


async def cache_delete_pattern(pattern: str) -> int:
    client = await get_redis()
    deleted = 0
    async for key in client.scan_iter(match=pattern):
        await client.delete(key)
        deleted += 1
    return deleted


async def cache_push_list(key: str, value: Any, max_len: int = 20) -> None:
    client = await get_redis()
    serialized = json.dumps(value, default=str)
    pipe = client.pipeline()
    pipe.lpush(key, serialized)
    pipe.ltrim(key, 0, max_len - 1)
    await pipe.execute()


async def cache_get_list(key: str, start: int = 0, end: int = -1) -> list[Any]:
    client = await get_redis()
    items = await client.lrange(key, start, end)
    return [json.loads(item) for item in items]
