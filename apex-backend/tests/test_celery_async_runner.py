"""Tests for Celery persistent asyncio event loop."""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas import KillSwitchStatus, KillSwitchStatusSchema
from app.workers.async_runner import get_worker_event_loop, run_async, shutdown_worker_event_loop


async def _noop_coro() -> str:
    return "ok"


def test_run_async_reuses_same_loop_on_consecutive_calls() -> None:
    shutdown_worker_event_loop()
    try:
        loop1 = get_worker_event_loop()
        assert run_async(_noop_coro()) == "ok"
        loop2 = get_worker_event_loop()
        assert loop1 is loop2
        assert run_async(_noop_coro()) == "ok"
    finally:
        shutdown_worker_event_loop()


def test_evaluate_kill_switch_runs_twice_without_loop_error() -> None:
    shutdown_worker_event_loop()
    status = KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE)

    with patch("app.workers.tasks.kill_switch.load_from_cache", new_callable=AsyncMock):
        with patch("app.workers.tasks.kill_switch.evaluate", new_callable=AsyncMock, return_value=status):
            from app.workers.tasks import evaluate_kill_switch

            result1 = evaluate_kill_switch()
            result2 = evaluate_kill_switch()

    shutdown_worker_event_loop()

    assert result1["status"] == "INACTIVE"
    assert result2["status"] == "INACTIVE"
