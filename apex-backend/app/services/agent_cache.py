"""Cache agent consensus results to reduce Groq API calls."""

from __future__ import annotations

import hashlib
import json

from app.config import settings
from app.core.redis_client import cache_delete_pattern, cache_get, cache_set
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
        "account_mode": mode,
        "account_balance": round(snapshot.account_balance, 2),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"apex:agent_llm_cache:{snapshot.symbol}:{digest}"


async def invalidate_agent_llm_cache() -> None:
    await cache_delete_pattern("apex:agent_llm_cache:*")


async def get_cached_consensus(snapshot: MarketSnapshot) -> AgentConsensus | None:
    try:
        raw = await cache_get(await _cache_key(snapshot))
    except Exception:
        return None
    if not raw:
        return None
    try:
        return AgentConsensus(**raw)
    except Exception:
        return None


async def set_cached_consensus(snapshot: MarketSnapshot, consensus: AgentConsensus) -> None:
    try:
        await cache_set(
            await _cache_key(snapshot),
            consensus.model_dump(mode="json"),
            ttl=settings.agent_cache_ttl_seconds,
        )
    except Exception:
        return None
