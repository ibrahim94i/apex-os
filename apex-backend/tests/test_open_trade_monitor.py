"""Tests for open trade monitor — news and SL warnings."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.open_trade_monitor_service import (
    _mark_trade_warning_sent,
    _trade_warning_already_sent,
    is_contrary_news,
    is_near_stop_loss,
    is_news_opinion_changed,
    register_open_trade_monitor,
    run_open_trade_monitor_cycle,
    warning_detail_ar,
)


def test_is_contrary_news_long_vs_short() -> None:
    assert is_contrary_news("LONG", "SHORT") is True
    assert is_contrary_news("SHORT", "LONG") is True
    assert is_contrary_news("LONG", "LONG") is False
    assert is_contrary_news("LONG", "NEUTRAL") is False


def test_is_news_opinion_changed() -> None:
    assert is_news_opinion_changed("LONG", "SHORT") is True
    assert is_news_opinion_changed("LONG", "LONG") is False
    assert is_news_opinion_changed("NEUTRAL", "SHORT") is False


def test_is_near_stop_loss_long() -> None:
    assert is_near_stop_loss(
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        current_price=96.0,
        near_ratio=0.25,
    )
    assert not is_near_stop_loss(
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        current_price=98.0,
        near_ratio=0.25,
    )


def test_is_near_stop_loss_short() -> None:
    assert is_near_stop_loss(
        direction="SHORT",
        entry_price=100.0,
        stop_loss=105.0,
        current_price=104.0,
        near_ratio=0.25,
    )


def test_warning_detail_ar() -> None:
    assert "الاتجاه تغير" in warning_detail_ar("contrary_news")
    assert "وقف الخسارة" in warning_detail_ar("near_sl")


@pytest.mark.asyncio
async def test_register_open_trade_monitor_stores_baseline() -> None:
    with patch(
        "app.services.open_trade_monitor_service.get_news_verdict",
        new=AsyncMock(return_value={"direction": "LONG"}),
    ):
        with patch(
            "app.services.open_trade_monitor_service.set_open_trade_monitor_state",
            new=AsyncMock(),
        ) as mock_set:
            await register_open_trade_monitor(
                journal_id=7,
                symbol="XAUUSD",
                trade_direction="LONG",
            )
    mock_set.assert_awaited_once()
    payload = mock_set.await_args.args[1]
    assert payload["news_direction_at_open"] == "LONG"
    assert payload["warnings_sent"] == []


@pytest.mark.asyncio
async def test_trade_warning_sent_once_per_trade_lifetime() -> None:
    state = {"journal_id": 7, "warnings_sent": []}
    with patch(
        "app.services.open_trade_monitor_service.open_trade_warning_already_sent",
        new=AsyncMock(return_value=False),
    ):
        with patch(
            "app.services.open_trade_monitor_service.set_open_trade_monitor_state",
            new=AsyncMock(),
        ) as mock_set:
            with patch(
                "app.services.open_trade_monitor_service.mark_open_trade_warning_sent",
                new=AsyncMock(),
            ) as mock_mark:
                await _mark_trade_warning_sent(
                    journal_id=7,
                    warning_type="near_sl",
                    state=state,
                )
    payload = mock_set.await_args.args[1]
    assert payload["warnings_sent"] == ["near_sl"]
    mock_mark.assert_awaited_once()

    with patch(
        "app.services.open_trade_monitor_service.open_trade_warning_already_sent",
        new=AsyncMock(return_value=False),
    ):
        already = await _trade_warning_already_sent(
            journal_id=7,
            warning_type="near_sl",
            state=payload,
        )
    assert already is True


@pytest.mark.asyncio
async def test_run_open_trade_monitor_cycle_resolves_and_warns() -> None:
    with patch(
        "app.services.open_trade_monitor_service.auto_outcome_tracker.track_pending_outcomes",
        new=AsyncMock(return_value=1),
    ):
        with patch(
            "app.services.open_trade_monitor_service._load_pending_open_trades",
            new=AsyncMock(return_value=[]),
        ):
            stats = await run_open_trade_monitor_cycle(session=AsyncMock())
    assert stats == {"resolved": 1, "warnings_sent": 0}
