"""Market analyst prompt includes SNR block."""

from datetime import datetime, timezone

from app.agents.market_analyst.prompt import build_user_prompt
from app.schemas.agent import MarketSnapshot
from app.schemas.enums import KillSwitchStatus, RegimeType, SignalDirection
from app.schemas.snr import SNRSnapshotSchema
from app.schemas.snapshots import (
    IndicatorSnapshotSchema,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
)


def test_market_analyst_prompt_includes_snr() -> None:
    now = datetime.now(timezone.utc)
    snr = SNRSnapshotSchema(
        symbol="XAUUSD",
        timestamp=now,
        price=4400.0,
        support_1=4380.0,
        resistance_1=4420.0,
        distance_to_support_pct=0.45,
        distance_to_resistance_pct=0.45,
    )
    snapshot = MarketSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        price=4400.0,
        indicators=IndicatorSnapshotSchema(symbol="XAUUSD", timestamp=now, rsi=50.0),
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
        snr=snr,
    )
    prompt = build_user_prompt(snapshot)
    assert "SNR" in prompt
    assert "S1" in prompt
    assert "R1" in prompt
