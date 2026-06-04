"""Team discussion Groq fallback behavior."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.team_discussion import TeamDiscussionService
from app.schemas import IndicatorSnapshotSchema, KillSwitchStatus, RegimeSnapshotSchema, RegimeType
from app.schemas.agent import MarketSnapshot
from app.schemas.snapshots import KillSwitchStatusSchema
from app.utils.llm_client import LLMClientError


def _snapshot() -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    return MarketSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        price=2400.0,
        indicators=IndicatorSnapshotSchema(
            symbol="XAUUSD",
            timestamp=now,
            rsi=50.0,
            macd=1.0,
            macd_signal=0.5,
        ),
        regime=RegimeSnapshotSchema(
            symbol="XAUUSD",
            timestamp=now,
            regime=RegimeType.TRENDING_UP,
            confidence=0.7,
        ),
        kill_switch=KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE),
        account_balance=10000.0,
        max_risk_pct=1.0,
        max_drawdown_pct=5.0,
    )


@pytest.mark.asyncio
async def test_team_discussion_fallback_sets_error_on_verdicts() -> None:
    service = TeamDiscussionService()
    service.client = MagicMock()
    service.client.is_configured = True
    service.client.structured_completion = AsyncMock(
        side_effect=LLMClientError("LLM request failed after retries: timeout")
    )

    verdicts, used_llm, error, _, _ = await service.analyze(_snapshot())

    assert used_llm is False
    assert error is not None
    assert len(verdicts) == 3
    assert all(v.error == error for v in verdicts)
    assert all(not v.used_llm for v in verdicts)
