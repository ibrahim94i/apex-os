"""Telegram signal alert — SNR explainability, collective confidence, live price."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.schemas import RegimeType, SignalDirection, TradingSignalSchema
from app.schemas.agent import AgentConsensus
from app.services.telegram_notifier import TelegramNotifier


def _consensus(confidence: float = 0.76) -> AgentConsensus:
    return AgentConsensus(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        final_direction=SignalDirection.SHORT,
        final_confidence=confidence,
        verdicts=[],
        vote_scores={},
        reasoning_summary=[],
    )


@pytest.mark.asyncio
async def test_telegram_includes_snr_explain(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    async def fake_send(text: str) -> bool:
        sent.append(text)
        return True

    notifier = TelegramNotifier()
    monkeypatch.setattr(notifier, "_send", fake_send)
    monkeypatch.setattr("app.services.telegram_notifier.settings.telegram_bot_token", "test-token")
    monkeypatch.setattr("app.services.telegram_notifier.settings.telegram_chat_id", "12345")
    monkeypatch.setattr(
        "app.services.telegram_notifier.fetch_twelvedata_live_close",
        AsyncMock(return_value=4375.50),
    )

    signal = TradingSignalSchema(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        direction=SignalDirection.SHORT,
        confidence=0.82,
        entry_price=4380.0,
        stop_loss=4395.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
        snr_explain_ar="بيع — Bearish Breakout تحت S1 عند 4380.00",
        snr_category="breakout",
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.82))

    assert sent
    assert "سبب الإشارة" in sent[0]
    assert "Bearish Breakout" in sent[0]
    assert "4375.5" in sent[0]
    assert "MetaTrader" in sent[0]


@pytest.mark.asyncio
async def test_telegram_uses_collective_confidence_after_snr(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    async def fake_send(text: str) -> bool:
        sent.append(text)
        return True

    async def fake_live_price(_symbol: str) -> float:
        return 2650.0

    notifier = TelegramNotifier()
    monkeypatch.setattr(notifier, "_send", fake_send)
    monkeypatch.setattr("app.services.telegram_notifier.settings.telegram_bot_token", "test-token")
    monkeypatch.setattr("app.services.telegram_notifier.settings.telegram_chat_id", "12345")
    monkeypatch.setattr(
        "app.services.telegram_notifier.fetch_twelvedata_live_close",
        fake_live_price,
    )

    signal = TradingSignalSchema(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        direction=SignalDirection.SHORT,
        confidence=0.58,
        entry_price=2655.0,
        stop_loss=2670.0,
        take_profit=2620.0,
        regime=RegimeType.TRENDING_DOWN,
    )
    sent_ok = await notifier.send_signal_alert(signal, consensus=_consensus(0.76))

    assert sent_ok is True
    assert sent
    assert "76.0%" in sent[0]
    assert "2650.0" in sent[0]


@pytest.mark.asyncio
async def test_telegram_blocked_when_collective_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []

    async def fake_send(text: str) -> bool:
        sent.append(text)
        return True

    notifier = TelegramNotifier()
    monkeypatch.setattr(notifier, "_send", fake_send)
    monkeypatch.setattr("app.services.telegram_notifier.settings.telegram_bot_token", "test-token")
    monkeypatch.setattr("app.services.telegram_notifier.settings.telegram_chat_id", "12345")

    signal = TradingSignalSchema(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        direction=SignalDirection.SHORT,
        confidence=0.82,
        entry_price=2655.0,
        stop_loss=2670.0,
        take_profit=2620.0,
        regime=RegimeType.TRENDING_DOWN,
    )
    sent_ok = await notifier.send_signal_alert(signal, consensus=_consensus(0.65))

    assert sent_ok is False
    assert not sent
