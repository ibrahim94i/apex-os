"""Pipeline orchestrator — processes incoming bars through the full engine stack."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.agents.orchestrator import agent_orchestrator
from app.core.cache import (
    set_agent_consensus,
    set_dashboard_state,
    set_latest_indicators,
    set_latest_regime,
    set_latest_signal,
)
from app.database import AsyncSessionLocal
from app.engines.candlestick_engine import candlestick_engine
from app.engines.indicator_engine import OHLCVBar
from app.engines.kill_switch import kill_switch
from app.engines.signal_generator import SignalGenerator
from app.logging_config import logger
from app.models import IndicatorSnapshot, PriceBar, RegimeSnapshot, TradingSignal
from app.schemas import (
    AgentConsensus,
    RegimeSnapshotSchema,
    RegimeType,
    SignalDirection,
    KillSwitchStatusSchema,
    TradingSignalSchema,
)
from app.services.signal_rejection_i18n import rejection_reason_ar
from app.services.alert_service import alert_service
from app.services.dashboard_builder import build_asset_dashboard_state
from app.services.market_hours import is_market_open
from app.services.market_snapshot import bind_indicator_regime_to_symbol, build_market_snapshot
from app.services.market_status_service import build_market_status
from app.services.signal_filters import apply_high_selectivity_filters
from app.services.signal_gate import should_emit_new_signal
from app.services.economic_calendar_gate import check_economic_calendar_gate
from app.services.finnhub_calendar import _load_high_impact_events
from app.services.safety_gate import check_mandatory_safety_gate
from app.services.position_service import detect_position_signal_conflict, get_open_positions
from app.config import settings
from app.services.telegram_notifier import telegram_notifier
from app.websocket.manager import broadcaster

_bar_buffer: dict[str, list[OHLCVBar]] = {}
MAX_BUFFER = 250
signal_generator = SignalGenerator()


def _parse_bar(raw: dict[str, Any]) -> OHLCVBar:
    ts = raw["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return OHLCVBar(
        timestamp=ts,
        open=raw["open"],
        high=raw["high"],
        low=raw["low"],
        close=raw["close"],
        volume=raw.get("volume", 0.0),
    )


async def _persist_bar(session: Any, bar: dict[str, Any]) -> None:
    ts = bar["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)

    stmt = insert(PriceBar).values(
        symbol=bar["symbol"],
        source=bar["source"],
        timestamp=ts,
        open=bar["open"],
        high=bar["high"],
        low=bar["low"],
        close=bar["close"],
        volume=bar.get("volume", 0.0),
    ).on_conflict_do_nothing(index_elements=["symbol", "timestamp"])
    await session.execute(stmt)


async def get_symbol_ohlcv_bars(symbol: str, limit: int = MAX_BUFFER) -> list[OHLCVBar]:
    """Return in-memory OHLCV buffer or load recent bars from DB."""
    if symbol in _bar_buffer and len(_bar_buffer[symbol]) >= 5:
        return _bar_buffer[symbol]
    from app.services.market_data_store import fetch_bars_from_db

    raw = await fetch_bars_from_db(symbol, limit)
    if not raw:
        return _bar_buffer.get(symbol, [])
    seed_bars_to_buffer(raw)
    return _bar_buffer.get(symbol, [])


def seed_bars_to_buffer(raw_bars: list[dict[str, Any]]) -> None:
    """Pre-fill bar buffer from historical data (no pipeline side effects)."""
    if not raw_bars:
        return
    symbol = raw_bars[0]["symbol"]
    if symbol not in _bar_buffer:
        _bar_buffer[symbol] = []
    for raw in raw_bars:
        _bar_buffer[symbol].append(_parse_bar(raw))
    if len(_bar_buffer[symbol]) > MAX_BUFFER:
        _bar_buffer[symbol] = _bar_buffer[symbol][-MAX_BUFFER:]


async def process_bar(raw_bar: dict[str, Any], *, skip_agents: bool = False) -> None:
    symbol = raw_bar["symbol"]

    if not is_market_open(symbol):
        logger.debug("market_closed_skip", symbol=symbol)
        status = await build_market_status(symbol)
        dashboard = await build_asset_dashboard_state(symbol)
        dash_data = dashboard.model_dump(mode="json")
        await set_dashboard_state(symbol, dash_data)
        await broadcaster.broadcast_dashboard_update(dash_data)
        await broadcaster.broadcast_market_status({symbol: status.model_dump(mode="json")})
        return

    ohlcv = _parse_bar(raw_bar)

    if symbol not in _bar_buffer:
        _bar_buffer[symbol] = []
    _bar_buffer[symbol].append(ohlcv)
    if len(_bar_buffer[symbol]) > MAX_BUFFER:
        _bar_buffer[symbol] = _bar_buffer[symbol][-MAX_BUFFER:]

    await broadcaster.broadcast_price({"symbol": symbol, "price": raw_bar["close"], "timestamp": raw_bar["timestamp"]})

    if not raw_bar.get("is_closed", True):
        return

    async with AsyncSessionLocal() as session:
        try:
            await _persist_bar(session, raw_bar)
            await kill_switch.load_from_cache()
            ks_status = await kill_switch.evaluate(session)

            from app.services.backtester import backtester

            await backtester.evaluate_pending_signals(session, symbol)

            indicators, regime = signal_generator.analyze(_bar_buffer[symbol], symbol)

            agent_consensus = None
            if indicators and regime and not skip_agents:
                indicators, regime = bind_indicator_regime_to_symbol(symbol, indicators, regime)
                candle_patterns = candlestick_engine.detect(_bar_buffer[symbol])
                snapshot = await build_market_snapshot(
                    symbol=symbol,
                    price=raw_bar["close"],
                    indicators=indicators,
                    regime=regime,
                    kill_switch=ks_status,
                    candlestick_patterns=candle_patterns,
                )
                agent_consensus = await agent_orchestrator.run(snapshot, session=session)

            signal = None
            signal_decision = "none"
            rejection_reason: str | None = None
            proposed_direction: SignalDirection | None = None
            proposed_confidence: float | None = None

            if indicators and regime and agent_consensus:
                if (
                    regime.regime == RegimeType.RANGING
                    and agent_consensus.final_direction == SignalDirection.NEUTRAL
                ):
                    signal_decision = "wait"
                    rejection_reason = "ranging_market_wait"
                elif agent_consensus.final_direction == SignalDirection.NEUTRAL:
                    rejection_reason = "neutral_direction"
                elif agent_consensus.final_direction != SignalDirection.NEUTRAL:
                    from app.services.account_service import account_service

                    proposed_direction = agent_consensus.final_direction
                    proposed_confidence = agent_consensus.final_confidence
                    balance = await account_service.get_balance()
                    signal = signal_generator.build_trading_signal(
                        _bar_buffer[symbol],
                        symbol,
                        agent_consensus.final_direction,
                        agent_consensus.final_confidence,
                        indicators,
                        regime,
                        kill_switch_active=kill_switch.is_active,
                        require_min_confidence=True,
                        account_balance=balance,
                    )
                    if signal:
                        safe, safety_reason = check_mandatory_safety_gate(
                            agent_consensus.final_direction,
                            regime,
                            indicators,
                            raw_bar["close"],
                        )
                        if not safe:
                            logger.info(
                                "safety_gate_blocked",
                                symbol=symbol,
                                reason=safety_reason,
                            )
                            signal_decision = "blocked"
                            rejection_reason = safety_reason
                            signal = None

                    if signal:
                        calendar_pool = await _load_high_impact_events()
                        cal_safe, cal_reason = check_economic_calendar_gate(
                            calendar_pool,
                            snapshot.timestamp,
                        )
                        if not cal_safe:
                            logger.info(
                                "economic_calendar_gate_blocked",
                                symbol=symbol,
                                reason=cal_reason,
                            )
                            signal_decision = "blocked"
                            rejection_reason = cal_reason
                            signal = None

                    if signal:
                        allowed, reason = await apply_high_selectivity_filters(
                            symbol,
                            agent_consensus.final_direction,
                            signal.confidence,
                            indicators,
                            regime,
                            _bar_buffer[symbol],
                            agent_consensus,
                        )
                        if not allowed:
                            logger.info(
                                "selectivity_wait",
                                symbol=symbol,
                                reason=reason,
                                confidence=signal.confidence,
                            )
                            signal_decision = "wait"
                            rejection_reason = reason or "selectivity_wait"
                            signal = None

                    if signal:
                        allowed, reason = await should_emit_new_signal(symbol, signal.entry_price)
                        if not allowed:
                            logger.info(
                                "signal_suppressed",
                                symbol=symbol,
                                reason=reason,
                                confidence=signal.confidence,
                            )
                            signal_decision = "wait"
                            rejection_reason = reason or "signal_suppressed"
                            signal = None

                    if signal:
                        signal_decision = "emitted"
                    elif signal_decision == "none" and rejection_reason is None:
                        signal_decision = "wait"
                        rejection_reason = "selectivity_wait"

            if agent_consensus and agent_consensus.is_llm_powered():
                agent_consensus = agent_consensus.model_copy(
                    update={
                        "signal_decision": signal_decision,
                        "rejection_reason": rejection_reason,
                        "rejection_reason_ar": rejection_reason_ar(rejection_reason),
                        "proposed_direction": proposed_direction,
                        "proposed_confidence": proposed_confidence,
                    }
                )
                consensus_data = agent_consensus.model_dump(mode="json")
                await set_agent_consensus(symbol, consensus_data)
                await broadcaster.broadcast_agent_consensus(consensus_data)

            if indicators:
                ind_data = indicators.model_dump(mode="json")
                await set_latest_indicators(symbol, ind_data)
                session.add(IndicatorSnapshot(
                    symbol=symbol,
                    timestamp=indicators.timestamp,
                    rsi=indicators.rsi,
                    macd=indicators.macd,
                    macd_signal=indicators.macd_signal,
                    macd_histogram=indicators.macd_histogram,
                    ema_9=indicators.ema_9,
                    ema_21=indicators.ema_21,
                    ema_50=indicators.ema_50,
                    ema_200=indicators.ema_200,
                    atr=indicators.atr,
                    atr_avg_20=indicators.atr_avg_20,
                    bb_upper=indicators.bb_upper,
                    bb_middle=indicators.bb_middle,
                    bb_lower=indicators.bb_lower,
                    adx=indicators.adx,
                ))

            if regime:
                reg_data = regime.model_dump(mode="json")
                await set_latest_regime(symbol, reg_data)
                await broadcaster.broadcast_regime(reg_data)
                session.add(RegimeSnapshot(
                    symbol=symbol,
                    timestamp=regime.timestamp,
                    regime=regime.regime.value,
                    confidence=regime.confidence,
                    adx_value=regime.adx_value,
                    volatility_pct=regime.volatility_pct,
                    trend_strength=regime.trend_strength,
                ))

            if signal:
                sig_data = signal.model_dump(mode="json")
                await set_latest_signal(symbol, sig_data)
                await broadcaster.broadcast_signal(sig_data)
                session.add(TradingSignal(
                    symbol=symbol,
                    timestamp=signal.timestamp,
                    direction=signal.direction.value,
                    confidence=signal.confidence,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    position_size=signal.position_size,
                    regime=signal.regime.value,
                    degraded=signal.degraded,
                    degradation_reason=signal.degradation_reason,
                    kill_switch_active=signal.kill_switch_active,
                ))

            await broadcaster.broadcast_kill_switch(ks_status.model_dump(mode="json"))
            await alert_service.check_kill_switch(
                ks_status.status.value == "ACTIVE", ks_status.reason
            )
            if ks_status.consecutive_losses:
                await alert_service.check_consecutive_losses(ks_status.consecutive_losses)

            if signal:
                open_positions = await get_open_positions(session, symbol)
                conflict, alert_type = detect_position_signal_conflict(
                    open_positions,
                    signal.direction.value,
                    signal.confidence,
                    threshold=settings.emergency_signal_confidence_threshold,
                )
                if conflict and alert_type:
                    open_dir = open_positions[0].direction if open_positions else ""
                    await telegram_notifier.send_emergency_position_warning(
                        symbol,
                        alert_type,
                        signal.confidence,
                        open_dir,
                        signal.direction.value,
                    )

                await alert_service.notify_new_signal(
                    symbol, signal.direction.value, signal.confidence
                )
                await alert_service.check_high_confidence(
                    symbol, signal.direction.value, signal.confidence
                )
                market_status = await build_market_status(symbol)
                await telegram_notifier.send_signal_alert(
                    signal,
                    market_status_ar=market_status.schedule_ar if market_status.is_open else "مغلق",
                    consensus=agent_consensus,
                )

            from app.core.cache import get_signal_history, get_agent_consensus

            history = await get_signal_history(symbol, 20)
            cached_consensus = await get_agent_consensus(symbol)
            market_status = await build_market_status(symbol)
            dashboard = await build_asset_dashboard_state(symbol)
            dashboard = dashboard.model_copy(
                update={
                    "regime": RegimeSnapshotSchema(**regime.model_dump()) if regime else None,
                    "latest_signal": TradingSignalSchema(**signal.model_dump()) if signal else dashboard.latest_signal,
                    "kill_switch": KillSwitchStatusSchema(**ks_status.model_dump()),
                    "signal_history": [TradingSignalSchema(**s) for s in history],
                    "current_price": raw_bar["close"],
                    "agent_consensus": AgentConsensus(**cached_consensus) if cached_consensus else agent_consensus,
                    "market_status": market_status,
                }
            )
            dash_data = dashboard.model_dump(mode="json")
            await set_dashboard_state(symbol, dash_data)
            await broadcaster.broadcast_dashboard_update(dash_data)

            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("pipeline_error", error=str(exc), symbol=symbol)
