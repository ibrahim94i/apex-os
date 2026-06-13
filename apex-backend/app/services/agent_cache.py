"""Cache agent consensus results to reduce Groq API calls."""

from __future__ import annotations

import hashlib
import json

from app.config import settings
from app.core.redis_client import cache_delete_pattern, cache_get, cache_set
from app.logging_config import logger
from app.schemas.agent import AgentConsensus, MarketSnapshot
from app.services.account_service import account_service


async def _cache_key(snapshot: MarketSnapshot) -> str:
    mode = await account_service.get_mode()
    ind = snapshot.indicators
    payload = {
        "symbol": snapshot.symbol,
        "price": round(snapshot.price, 5),
        "ind_ts": ind.timestamp.isoformat() if ind.timestamp else "",
        "regime": snapshot.regime.regime.value,
        "rsi": round(ind.rsi or 0, 2),
        "macd": round(ind.macd or 0, 6),
        "ema_50": round(ind.ema_50 or 0, 5),
        "atr": round(ind.atr or 0, 6),
        "adx": round(ind.adx or 0, 2),
        "account_mode": mode,
        "account_balance": round(snapshot.account_balance, 2),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"apex:agent_llm_cache:{snapshot.symbol}:{digest}"


async def invalidate_agent_llm_cache() -> None:
    try:
        await cache_delete_pattern("apex:agent_llm_cache:*")
    except Exception as exc:
        logger.warning("agent_llm_cache_invalidation_failed", error=str(exc))


async def get_cached_consensus(snapshot: MarketSnapshot) -> AgentConsensus | None:
    try:
        raw = await cache_get(await _cache_key(snapshot))
    except Exception:
        return None
    if not raw:
        return None
    try:
        cached = AgentConsensus(**raw)
    except Exception:
        return None
    if cached.symbol != snapshot.symbol:
        return None
    return cached


async def set_cached_consensus(
    snapshot: MarketSnapshot,
    consensus: AgentConsensus,
    *,
    ttl_seconds: int | None = None,
) -> None:
    try:
        bound = consensus.model_copy(update={"symbol": snapshot.symbol})
        await cache_set(
            await _cache_key(snapshot),
            bound.model_dump(mode="json"),
            ttl=ttl_seconds if ttl_seconds is not None else settings.agent_cache_ttl_seconds,
        )
    except Exception:
        return None
