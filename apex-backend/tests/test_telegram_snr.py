"""Telegram signal alert includes SNR explainability."""

from datetime import datetime, timezone

import pytest

from app.schemas import RegimeType, SignalDirection, TradingSignalSchema
from app.services.telegram_notifier import TelegramNotifier


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
    await notifier.send_signal_alert(signal)

    assert sent
    assert "سبب الإشارة" in sent[0]
    assert "Bearish Breakout" in sent[0]
    assert "4380" in sent[0]
