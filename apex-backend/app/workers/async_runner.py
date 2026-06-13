"""Persistent asyncio event loop for Celery sync tasks.

Celery tasks run in sync context. Creating a new event loop per task and closing
it breaks module-level async clients (SQLAlchemy engine, Redis) bound to the first loop.
Reuse one loop per worker process instead.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_worker_loop: asyncio.AbstractEventLoop | None = None


def get_worker_event_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    loop = get_worker_event_loop()
    return loop.run_until_complete(coro)


def shutdown_worker_event_loop() -> None:
    """Dispose async resources and close the worker loop on process exit."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = None
        return

    async def _cleanup() -> None:
        from app.core.redis_client import close_redis
        from app.database import engine

        await close_redis()
        await engine.dispose()

    try:
        _worker_loop.run_until_complete(_cleanup())
    finally:
        _worker_loop.close()
        _worker_loop = None
        asyncio.set_event_loop(None)
