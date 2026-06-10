"""Redis-backed OpenAI circuit breaker — 1 hour pause on 429, single half-open probe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from app.config import settings
from app.core.redis_client import cache_delete, cache_get, cache_set
from app.logging_config import logger

_REDIS_KEY = "apex:llm_circuit_breaker"
_PROBE_KEY = "apex:llm_half_open_probe"


class LLMCircuitOpenError(Exception):
    """Raised when LLM calls are blocked by the circuit breaker."""


class LLMCircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class LLMCircuitStatus:
    state: LLMCircuitState
    open_until: datetime | None = None
    remaining_seconds: int | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _load_raw() -> dict:
    raw = await cache_get(_REDIS_KEY)
    return raw if isinstance(raw, dict) else {}


async def get_circuit_status() -> LLMCircuitStatus:
    raw = await _load_raw()
    open_until = _parse_ts(raw.get("open_until"))
    if not open_until:
        return LLMCircuitStatus(state=LLMCircuitState.CLOSED)

    now = _utcnow()
    if now < open_until:
        remaining = int((open_until - now).total_seconds())
        return LLMCircuitStatus(
            state=LLMCircuitState.OPEN,
            open_until=open_until,
            remaining_seconds=max(remaining, 0),
        )
    return LLMCircuitStatus(state=LLMCircuitState.HALF_OPEN, open_until=open_until)


async def is_llm_blocked() -> bool:
    """True only while the circuit is fully open (hour-long pause)."""
    status = await get_circuit_status()
    return status.state == LLMCircuitState.OPEN


async def acquire_half_open_probe() -> bool:
    """Allow exactly one LLM attempt after the open window expires."""
    status = await get_circuit_status()
    if status.state != LLMCircuitState.HALF_OPEN:
        return status.state == LLMCircuitState.CLOSED

    from app.core.redis_client import get_redis

    client = await get_redis()
    acquired = await client.set(_PROBE_KEY, "1", nx=True, ex=300)
    if acquired:
        logger.info("llm_circuit_half_open_probe_acquired")
    return bool(acquired)


async def assert_llm_allowed() -> None:
    """Raise LLMCircuitOpenError when LLM calls must not run."""
    status = await get_circuit_status()
    if status.state == LLMCircuitState.CLOSED:
        return
    if status.state == LLMCircuitState.OPEN:
        raise LLMCircuitOpenError(
            f"LLM circuit open until {status.open_until.isoformat() if status.open_until else 'unknown'}"
        )
    if await acquire_half_open_probe():
        return
    raise LLMCircuitOpenError("LLM half-open probe already in flight")


async def open_llm_circuit(*, reason: str = "429") -> datetime:
    """Block all LLM calls for one hour."""
    open_until = _utcnow() + timedelta(seconds=settings.llm_circuit_open_seconds)
    await cache_set(
        _REDIS_KEY,
        {
            "open_until": open_until.isoformat(),
            "reason": reason,
            "opened_at": _utcnow().isoformat(),
        },
        ttl=settings.llm_circuit_open_seconds + 7200,
    )
    await cache_delete(_PROBE_KEY)
    logger.warning(
        "llm_circuit_opened",
        reason=reason,
        open_until=open_until.isoformat(),
        pause_seconds=settings.llm_circuit_open_seconds,
    )
    return open_until


async def close_llm_circuit() -> None:
    await cache_delete(_REDIS_KEY)
    await cache_delete(_PROBE_KEY)
    logger.info("llm_circuit_closed")


async def record_llm_success() -> None:
    await close_llm_circuit()


async def record_llm_429() -> None:
    await open_llm_circuit(reason="429")


async def record_llm_probe_failure() -> None:
    """Half-open probe failed — open circuit for another hour."""
    await open_llm_circuit(reason="429_probe_failed")


async def clear_llm_circuit() -> None:
    """Test helper."""
    await close_llm_circuit()


async def get_circuit_report() -> dict[str, str | int | bool | None]:
    status = await get_circuit_status()
    return {
        "state": status.state.value,
        "open_until": status.open_until.isoformat() if status.open_until else None,
        "remaining_seconds": status.remaining_seconds,
        "blocked": await is_llm_blocked(),
    }
