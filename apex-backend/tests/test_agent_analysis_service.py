"""Tests for agent analysis when consensus is missing from cache."""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas import SignalDirection
from app.schemas.agent import AgentConsensus, AgentRole, AgentVerdict
from app.services.agent_analysis_service import run_agent_analysis


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
            )
        ],
        vote_scores={"market_analyst": -0.2},
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
            "app.services.agent_analysis_service.get_agent_consensus",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "app.services.agent_analysis_service.get_latest_price",
                new_callable=AsyncMock,
                return_value=None,
            ):
                result = await run_agent_analysis("XAUUSD")
    assert result is None


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

    with patch("app.services.agent_analysis_service.is_market_open", return_value=True):
        with patch(
            "app.services.agent_analysis_service.get_agent_consensus",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "app.services.agent_analysis_service.get_latest_price",
                new_callable=AsyncMock,
                return_value=price,
            ):
                with patch(
                    "app.services.agent_analysis_service.get_latest_indicators",
                    new_callable=AsyncMock,
                    return_value=indicators,
                ):
                    with patch(
                        "app.services.agent_analysis_service.get_latest_regime",
                        new_callable=AsyncMock,
                        return_value=regime,
                    ):
                        with patch(
                            "app.services.agent_analysis_service.AsyncSessionLocal"
                        ) as mock_local:
                            mock_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                            mock_local.return_value.__aexit__ = AsyncMock(return_value=False)
                            with patch(
                                "app.services.agent_analysis_service.kill_switch"
                            ) as mock_ks:
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
                                with patch(
                                    "app.services.agent_analysis_service.build_market_snapshot",
                                    new_callable=AsyncMock,
                                ) as mock_snapshot:
                                    mock_snapshot.return_value = AsyncMock()
                                    with patch(
                                        "app.services.agent_analysis_service.agent_orchestrator.run",
                                        new_callable=AsyncMock,
                                        return_value=consensus,
                                    ):
                                        with patch(
                                            "app.services.agent_analysis_service.set_agent_consensus",
                                            new_callable=AsyncMock,
                                        ) as mock_set:
                                            with patch(
                                                "app.services.agent_analysis_service.broadcaster.broadcast_agent_consensus",
                                                new_callable=AsyncMock,
                                            ) as mock_broadcast:
                                                result = await run_agent_analysis("XAUUSD")

    assert result is not None
    mock_set.assert_awaited_once()
    mock_broadcast.assert_awaited_once()
    mock_session.commit.assert_awaited_once()
