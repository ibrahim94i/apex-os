"""Tests for agent analysis when consensus is missing from cache."""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas import SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict
from app.schemas import IndicatorSnapshotSchema, RegimeSnapshotSchema
from app.services.agent_analysis_service import (
    run_agent_analysis,
    _load_market_context,
    _restore_stale_consensus,
)


def _sample_consensus() -> AgentConsensus:
    return AgentConsensus(
        symbol="XAUUSD",
        timestamp="2026-06-04T01:00:00+00:00",
        final_direction=SignalDirection.SHORT,
        final_confidence=0.58,
        verdicts=[
            AgentVerdict(
                agent_id=AgentRole.MARKET_ANALYST,
                agent_name_ar="محلل السوق",
                direction=SignalDirection.SHORT,
                confidence=0.7,
                reasoning=["اختبار"],
                weight=0.35,
                used_llm=True,
            )
        ],
        vote_scores={"market_analyst": -0.2},
        snr_state="NORMAL",
        snr_state_ar="عادي",
    )


@pytest.mark.asyncio
async def test_run_agent_analysis_returns_cached_when_present() -> None:
    cached = _sample_consensus().model_dump(mode="json")
    with patch("app.services.agent_analysis_service.is_market_open", return_value=True):
        with patch(
            "app.services.agent_analysis_service.get_agent_consensus",
            new_callable=AsyncMock,
            return_value=cached,
        ):
            result = await run_agent_analysis("XAUUSD")
    assert result is not None
    assert result.final_direction == SignalDirection.SHORT


@pytest.mark.asyncio
async def test_run_agent_analysis_skips_without_warm_data() -> None:
    with patch("app.services.agent_analysis_service.is_market_open", return_value=True):
        with patch(
            "app.services.agent_analysis_service._serve_stale_if_llm_blocked",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "app.services.agent_analysis_service.get_agent_consensus",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch(
                    "app.services.agent_analysis_service._load_market_context",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    result = await run_agent_analysis("EURUSD")
    assert result is None


@pytest.mark.asyncio
async def test_load_market_context_recomputes_indicators_from_db() -> None:
    from app.services.agent_analysis_service import _load_market_context

    bars = [
        {
            "symbol": "EURUSD",
            "timestamp": f"2026-01-{(i // 24) + 1:02d}T{i % 24:02d}:00:00+00:00",
            "open": 1.1,
            "high": 1.11,
            "low": 1.09,
            "close": 1.1,
            "volume": 0.0,
            "source": "twelvedata",
            "is_closed": True,
        }
        for i in range(250)
    ]
    ind = {
        "symbol": "EURUSD",
        "timestamp": "2026-02-01T00:00:00+00:00",
        "rsi": 50.0,
        "macd": 0.0,
        "macd_signal": 0.0,
        "macd_histogram": 0.0,
        "ema_9": 1.1,
        "ema_21": 1.1,
        "ema_50": 1.1,
        "ema_200": 1.1,
        "atr": 0.001,
        "atr_avg_20": 0.001,
        "bb_upper": 1.11,
        "bb_middle": 1.1,
        "bb_lower": 1.09,
        "adx": 25.0,
    }
    reg = {
        "symbol": "EURUSD",
        "timestamp": "2026-02-01T00:00:00+00:00",
        "regime": "TRENDING_DOWN",
        "confidence": 0.6,
        "adx_value": 25.0,
        "volatility_pct": 0.05,
        "trend_strength": -0.2,
    }

    with patch(
        "app.services.agent_analysis_service.get_latest_price",
        new_callable=AsyncMock,
        return_value={"price": 1.1608, "timestamp": "2026-02-01T00:00:00+00:00"},
    ):
        with patch(
            "app.services.agent_analysis_service.get_latest_regime",
            new_callable=AsyncMock,
            return_value=reg,
        ):
            with patch(
                "app.services.agent_analysis_service.get_latest_indicators",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch(
                    "app.services.agent_analysis_service.fetch_bars_from_db",
                    new_callable=AsyncMock,
                    return_value=bars,
                ):
                    with patch(
                        "app.services.agent_analysis_service._signal_generator.analyze",
                        return_value=(IndicatorSnapshotSchema(**ind), RegimeSnapshotSchema(**reg)),
                    ):
                        with patch(
                            "app.services.agent_analysis_service.set_latest_indicators",
                            new_callable=AsyncMock,
                        ):
                            with patch(
                                "app.services.agent_analysis_service.set_latest_regime",
                                new_callable=AsyncMock,
                            ):
                                ctx = await _load_market_context("EURUSD")

    assert ctx is not None
    assert ctx[1]["symbol"] == "EURUSD"


@pytest.mark.asyncio
async def test_run_agent_analysis_publishes_consensus() -> None:
    consensus = _sample_consensus()
    price = {"price": 4450.0, "timestamp": "2026-06-04T11:00:00Z"}
    indicators = {
        "symbol": "XAUUSD",
        "timestamp": "2026-06-04T11:00:00Z",
        "rsi": 51.0,
        "macd": 1.0,
        "macd_signal": 0.5,
        "macd_histogram": 0.5,
        "ema_9": 4440.0,
        "ema_21": 4450.0,
        "ema_50": 4460.0,
        "ema_200": 4480.0,
        "atr": 10.0,
        "atr_avg_20": 9.0,
        "bb_upper": 4500.0,
        "bb_middle": 4450.0,
        "bb_lower": 4400.0,
        "adx": 30.0,
    }
    regime = {
        "symbol": "XAUUSD",
        "timestamp": "2026-06-04T11:00:00Z",
        "regime": "TRENDING_DOWN",
        "confidence": 0.6,
        "adx_value": 30.0,
        "volatility_pct": 0.2,
        "trend_strength": -0.3,
    }

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    patches = [
        patch("app.services.agent_analysis_service.is_market_open", return_value=True),
        patch(
            "app.services.agent_analysis_service._serve_stale_if_llm_blocked",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.agent_analysis_service.get_agent_consensus",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.agent_analysis_service._load_market_context",
            new_callable=AsyncMock,
            return_value=(price, indicators, regime),
        ),
        patch(
            "app.services.agent_analysis_service.is_feed_poll_stale",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.agent_analysis_service.build_market_snapshot",
            new_callable=AsyncMock,
            return_value=AsyncMock(),
        ),
            patch(
                "app.services.agent_analysis_service.agent_orchestrator.run_h1",
                new_callable=AsyncMock,
                return_value=consensus,
            ),
        patch(
            "app.services.agent_analysis_service.set_agent_consensus_last_good",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.snr_service.enrich_consensus_with_snr",
            new_callable=AsyncMock,
            side_effect=lambda consensus, symbol, persist=False: consensus.model_copy(
                update={
                    "snr_state": "NORMAL",
                    "snr_state_ar": "عادي",
                    "final_decision": "SELL",
                    "final_decision_ar": "بيع",
                }
            ),
        ),
    ]

    from contextlib import ExitStack

    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        mock_local = stack.enter_context(
            patch("app.services.agent_analysis_service.AsyncSessionLocal")
        )
        mock_ks = stack.enter_context(patch("app.services.agent_analysis_service.kill_switch"))
        mock_set = stack.enter_context(
            patch(
                "app.services.agent_analysis_service.set_agent_consensus",
                new_callable=AsyncMock,
            )
        )
        mock_broadcast = stack.enter_context(
            patch(
                "app.services.agent_analysis_service.broadcaster.broadcast_agent_consensus",
                new_callable=AsyncMock,
            )
        )

        mock_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_local.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_ks.load_from_cache = AsyncMock()
        mock_ks.evaluate = AsyncMock(
            return_value=AsyncMock(
                model_dump=lambda **_: {
                    "status": "INACTIVE",
                    "reason": None,
                    "triggered_at": None,
                    "drawdown_pct": 0.0,
                    "daily_loss_pct": 0.0,
                    "consecutive_losses": 0,
                }
            )
        )

        result = await run_agent_analysis("XAUUSD")

    assert result is not None
    mock_set.assert_awaited_once()
    mock_broadcast.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_agent_analysis_skips_when_market_closed_and_flag_off() -> None:
    with patch("app.services.agent_analysis_service.settings.agents_run_when_market_closed", False):
        with patch("app.services.agent_analysis_service.is_market_open", return_value=False):
            result = await run_agent_analysis("XAUUSD", force=True)
    assert result is None


@pytest.mark.asyncio
async def test_run_agent_analysis_not_blocked_when_market_closed_for_testing() -> None:
    with patch("app.services.agent_analysis_service.is_market_open", return_value=False):
        with patch(
            "app.services.agent_analysis_service.get_agent_consensus",
            new_callable=AsyncMock,
            return_value=_sample_consensus().model_dump(mode="json"),
        ):
            result = await run_agent_analysis("XAUUSD")
    assert result is not None


@pytest.mark.asyncio
async def test_run_agent_analysis_does_not_cache_rule_based_fallback() -> None:
    rule_consensus = _sample_consensus().model_copy(
        update={
            "verdicts": [
                _sample_consensus().verdicts[0].model_copy(
                    update={"used_llm": False, "error": "timeout"}
                )
            ]
        }
    )
    assert not rule_consensus.is_llm_powered()

    llm_consensus = _sample_consensus()
    assert llm_consensus.is_llm_powered()


@pytest.mark.asyncio
async def test_restore_stale_consensus_on_429() -> None:
    last_good = _sample_consensus().model_dump(mode="json")

    with patch(
        "app.services.agent_analysis_service.get_agent_consensus",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch(
            "app.services.agent_analysis_service.get_agent_consensus_last_good",
            new_callable=AsyncMock,
            return_value=last_good,
        ):
            with patch(
                "app.services.agent_analysis_service.set_agent_consensus",
                new_callable=AsyncMock,
            ) as mock_set:
                with patch(
                    "app.services.agent_analysis_service.broadcaster.broadcast_agent_consensus",
                    new_callable=AsyncMock,
                ) as mock_broadcast:
                    result = await _restore_stale_consensus(
                        "XAUUSD",
                        "LLM request failed after retries: 429 Too Many Requests",
                    )

    assert result is not None
    assert result.is_stale is True
    assert result.stale_warning_ar == "بيانات قديمة"
    mock_set.assert_awaited_once()
    mock_broadcast.assert_awaited_once()
