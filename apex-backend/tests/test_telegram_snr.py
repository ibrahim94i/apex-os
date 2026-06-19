"""Telegram signal alert — entry zones, collective confidence, SNR explainability."""

from datetime import datetime, timezone

import pytest

from app.schemas import RegimeType, SignalDirection, TradingSignalSchema
from app.schemas.agent import AgentConsensus
from app.schemas.snr import SNRSnapshotSchema
from app.services.telegram_notifier import (
    INSIDE_ZONE_WARNING_AR,
    MACD_DIVERGENCE_WARNING_AR,
    TelegramNotifier,
)


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


def _snr() -> SNRSnapshotSchema:
    return SNRSnapshotSchema(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        price=4313.87,
        support_1=4295.0,
        resistance_1=4330.0,
    )


@pytest.mark.asyncio
async def test_telegram_shows_entry_zone(monkeypatch: pytest.MonkeyPatch) -> None:
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
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
        snr_explain_ar="بيع — Bearish Breakout تحت منطقة S1",
        snr_category="breakout",
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.82), snr=_snr())

    assert sent
    assert "منطقة الدخول" in sent[0]
    assert "4305" in sent[0]
    assert "4325" in sent[0]
    assert "4290" in sent[0]
    assert "4350" in sent[0]
    assert "MetaTrader داخل المنطقة" in sent[0]
    assert "📊 مستويات SNR:" in sent[0]
    assert "4330" in sent[0]
    assert "4295" in sent[0]
    assert "فوق الدخول" in sent[0]
    assert "تحت الدخول" in sent[0]


@pytest.mark.asyncio
async def test_telegram_uses_collective_confidence_after_snr(monkeypatch: pytest.MonkeyPatch) -> None:
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
        confidence=0.58,
        entry_price=2650.0,
        entry_zone_low=2643.0,
        entry_zone_high=2657.0,
        stop_loss=2635.0,
        take_profit=2670.0,
        regime=RegimeType.TRENDING_DOWN,
    )
    sent_ok = await notifier.send_signal_alert(signal, consensus=_consensus(0.76), snr=_snr())

    assert sent_ok is True
    assert "76.0%" in sent[0]
    assert INSIDE_ZONE_WARNING_AR not in sent[0]


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


@pytest.mark.asyncio
async def test_telegram_inside_zone_caps_confidence_and_shows_warning(
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
        confidence=0.70,
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
        snr_state="inside_zone",
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.82), snr=_snr())

    assert sent
    assert "60.0%" in sent[0]
    assert "82.0%" not in sent[0]
    assert INSIDE_ZONE_WARNING_AR in sent[0]


@pytest.mark.asyncio
async def test_telegram_breakout_confirmed_keeps_original_confidence(
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
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
        snr_state="breakout_confirmed",
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.82), snr=_snr())

    assert sent
    assert "82.0%" in sent[0]
    assert INSIDE_ZONE_WARNING_AR not in sent[0]


@pytest.mark.asyncio
async def test_telegram_macd_divergence_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
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
        confidence=0.70,
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
        degraded=True,
        degradation_reason="MACD divergence",
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.76), snr=_snr())

    assert sent
    assert MACD_DIVERGENCE_WARNING_AR in sent[0]


@pytest.mark.asyncio
async def test_telegram_no_macd_warning_without_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
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
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.82), snr=_snr())

    assert sent
    assert MACD_DIVERGENCE_WARNING_AR not in sent[0]


@pytest.mark.asyncio
async def test_telegram_macd_divergence_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
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
        confidence=0.70,
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
        degraded=True,
        degradation_reason="MACD divergence",
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.76), snr=_snr())

    assert sent
    assert MACD_DIVERGENCE_WARNING_AR in sent[0]


@pytest.mark.asyncio
async def test_telegram_no_macd_warning_without_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
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
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.82), snr=_snr())

    assert sent
    assert MACD_DIVERGENCE_WARNING_AR not in sent[0]


@pytest.mark.asyncio
async def test_telegram_macd_divergence_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
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
        confidence=0.70,
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
        degraded=True,
        degradation_reason="MACD divergence",
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.76), snr=_snr())

    assert sent
    assert MACD_DIVERGENCE_WARNING_AR in sent[0]


@pytest.mark.asyncio
async def test_telegram_no_macd_warning_without_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
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
        entry_price=4313.87,
        entry_zone_low=4305.0,
        entry_zone_high=4325.0,
        stop_loss=4290.0,
        take_profit=4350.0,
        regime=RegimeType.TRENDING_DOWN,
    )
    await notifier.send_signal_alert(signal, consensus=_consensus(0.82), snr=_snr())

    assert sent
    assert MACD_DIVERGENCE_WARNING_AR not in sent[0]
