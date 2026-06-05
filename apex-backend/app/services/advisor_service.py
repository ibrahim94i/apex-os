"""Smart Advisor — aggregates APEX data and calls GPT-4o-mini (APEX data only)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.config.assets import ACTIVE_SYMBOLS, ASSETS, get_asset
from app.core.cache import (
    get_agent_consensus,
    get_latest_indicators,
    get_latest_regime,
    get_latest_signal,
)
from app.logging_config import logger
from app.schemas.advisor import AdvisorAssetContext, AdvisorChatResponse, AdvisorContextResponse
from app.services.market_data_store import get_latest_regime_from_db
from app.services.market_snapshot import redis_snapshot_matches_symbol
from app.services.news_aggregator import fetch_news_for_symbol
from app.utils.llm_client import LLMClientError, llm_client

from app.services.advisor_price_resolver import resolve_advisor_price
from app.services.advisor_prompt import (
    ADVISOR_SYSTEM_PROMPT,
    DATA_UNAVAILABLE_MSG,
    INTRADAY_DISCLAIMER,
)


def _entry_band(price: float) -> tuple[float, float]:
    margin = price * 0.005
    return price - margin, price + margin


def _fmt_band(low: float, high: float, decimals: int) -> str:
    return f"{low:.{decimals}f} – {high:.{decimals}f}"


async def _build_intraday_block(symbol: str, ctx: AdvisorAssetContext) -> str:
    """Recent H1 bars, candle patterns, session, and entry band for intraday focus."""
    from app.engines.candlestick_engine import candlestick_engine
    from app.services.market_data_store import fetch_bars_from_db
    from app.services.market_status_service import build_market_status

    lines: list[str] = []
    market = await build_market_status(symbol)
    lines.append(f"السوق مفتوح: {'نعم' if market.is_open else 'لا'}")
    if market.schedule_ar:
        lines.append(f"جدول الجلسة: {market.schedule_ar}")

    if ctx.price is not None:
        dec = 2 if symbol == "XAUUSD" else (3 if symbol == "USDJPY" else 5)
        lo, hi = _entry_band(ctx.price)
        lines.append(f"السعر APEX ({ctx.price_source}): {_fmt(ctx.price, dec)}")
        lines.append(f"نطاق الدخول المسموح (±0.5%): {_fmt_band(lo, hi, dec)}")
        if ctx.price_age_minutes is not None and ctx.price_age_minutes > 0:
            lines.append(f"عمر السعر: {ctx.price_age_minutes:.1f} دقيقة")
    else:
        lines.append("السعر APEX: غير متاح أو قديم (>10 دقائق)")

    bars = await fetch_bars_from_db(symbol, limit=8)
    if bars:
        lines.append("آخر شموع H1 (O/H/L/C):")
        for bar in bars[-5:]:
            ts = str(bar.get("timestamp", ""))[:16]
            lines.append(
                f"  {ts} O={bar['open']} H={bar['high']} L={bar['low']} C={bar['close']}"
            )
        from app.engines.indicator_engine import OHLCVBar
        from app.utils.time_utils import parse_utc_timestamp

        ohlcv = [
            OHLCVBar(
                timestamp=parse_utc_timestamp(b["timestamp"]),
                open=float(b["open"]),
                high=float(b["high"]),
                low=float(b["low"]),
                close=float(b["close"]),
                volume=float(b.get("volume", 0)),
            )
            for b in bars
        ]
        patterns = candlestick_engine.detect(ohlcv)
        if patterns:
            pat_text = ", ".join(f"{p.name_ar} ({p.signal})" for p in patterns[:5])
            lines.append(f"أنماط الشموع: {pat_text}")
        else:
            lines.append("أنماط الشموع: لا نمط واضح على آخر الشموع")
        if len(bars) >= 2:
            prev_close = float(bars[-2]["close"])
            last_close = float(bars[-1]["close"])
            change_pct = ((last_close - prev_close) / prev_close) * 100 if prev_close else 0
            lines.append(f"زخم آخر شمعتين H1: {change_pct:+.3f}%")
    else:
        lines.append("شموع H1: غير متوفرة")

    if not ctx.data_complete:
        lines.append("⚠️ بيانات APEX ناقصة — لا توصية متاحة")

    return "\n".join(lines)


def _ensure_intraday_disclaimer(reply: str) -> str:
    if INTRADAY_DISCLAIMER in reply:
        return reply
    return f"{reply.rstrip()}\n\n{INTRADAY_DISCLAIMER}"


def _fmt(value: float | None, decimals: int = 5) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


async def _load_indicators(symbol: str) -> dict[str, Any] | None:
    ind_data = await get_latest_indicators(symbol)
    if ind_data and redis_snapshot_matches_symbol(symbol, ind_data):
        return ind_data

    from app.services.agent_analysis_service import _recompute_market_metrics

    recomputed_ind, _ = await _recompute_market_metrics(symbol)
    return recomputed_ind


async def build_asset_advisor_context(symbol: str) -> AdvisorAssetContext:
    asset = get_asset(symbol)
    display = asset.display_name_ar if asset else symbol
    feed_type = asset.feed_type if asset else None

    price_info = await resolve_advisor_price(symbol)

    regime_data = await get_latest_regime(symbol)
    if not regime_data:
        regime_data = await get_latest_regime_from_db(symbol)

    ind_data = await _load_indicators(symbol)
    consensus_data = await get_agent_consensus(symbol)
    signal_data = await get_latest_signal(symbol)
    news = await fetch_news_for_symbol(symbol)

    agent_direction = None
    agent_confidence = None
    agent_summary = None
    if consensus_data:
        agent_direction = consensus_data.get("final_direction")
        agent_confidence = consensus_data.get("final_confidence")
        agent_summary = consensus_data.get("team_discussion_summary")
        if not agent_summary:
            summary_list = consensus_data.get("reasoning_summary")
            if isinstance(summary_list, list) and summary_list:
                agent_summary = " | ".join(str(x) for x in summary_list[:3])
            else:
                agent_summary = consensus_data.get("collective_reasoning")

    signal_direction = None
    signal_confidence = None
    if signal_data:
        signal_direction = signal_data.get("direction")
        signal_confidence = signal_data.get("confidence")

    data_complete = bool(price_info.price is not None and ind_data and regime_data)

    return AdvisorAssetContext(
        symbol=symbol,
        display_name_ar=display,
        price=price_info.price,
        apex_price=price_info.apex_price,
        price_timestamp=price_info.price_timestamp,
        price_age_minutes=price_info.price_age_minutes,
        apex_price_stale=price_info.apex_price_stale,
        price_source=price_info.price_source,
        feed_type=feed_type,
        regime=regime_data.get("regime") if regime_data else None,
        regime_confidence=regime_data.get("confidence") if regime_data else None,
        adx=ind_data.get("adx") if ind_data else regime_data.get("adx_value") if regime_data else None,
        rsi=ind_data.get("rsi") if ind_data else None,
        macd=ind_data.get("macd") if ind_data else None,
        macd_signal=ind_data.get("macd_signal") if ind_data else None,
        ema_9=ind_data.get("ema_9") if ind_data else None,
        ema_21=ind_data.get("ema_21") if ind_data else None,
        ema_50=ind_data.get("ema_50") if ind_data else None,
        ema_200=ind_data.get("ema_200") if ind_data else None,
        agent_direction=agent_direction,
        agent_confidence=agent_confidence,
        agent_summary=str(agent_summary)[:500] if agent_summary else None,
        latest_signal_direction=signal_direction,
        latest_signal_confidence=signal_confidence,
        news_count=len(news),
        data_complete=data_complete,
    )


async def build_all_advisor_context() -> list[AdvisorAssetContext]:
    contexts: list[AdvisorAssetContext] = []
    for symbol in ACTIVE_SYMBOLS:
        try:
            contexts.append(await build_asset_advisor_context(symbol))
        except Exception as exc:
            logger.warning("advisor_context_build_failed", symbol=symbol, error=str(exc))
            contexts.append(
                AdvisorAssetContext(
                    symbol=symbol,
                    display_name_ar=ASSETS[symbol].display_name_ar,
                    data_complete=False,
                )
            )
    return contexts


def _format_apex_context(contexts: list[AdvisorAssetContext]) -> str:
    blocks: list[str] = []
    for ctx in contexts:
        headlines_note = f"{ctx.news_count} عنوان خبر جلسة" if ctx.news_count else "لا أخبار عاجلة"
        dec = 2 if ctx.symbol == "XAUUSD" else 5
        if ctx.price is not None:
            price_line = f"السعر APEX ({ctx.price_source}): {_fmt(ctx.price, dec)}"
        elif ctx.apex_price_stale and ctx.apex_price is not None:
            price_line = f"السعر: قديم/غير صالح — آخر APEX: {_fmt(ctx.apex_price, dec)}"
        else:
            price_line = "السعر: غير متاح"
        block = f"""
=== {ctx.symbol} ({ctx.display_name_ar}) ===
مصدر البيانات: {ctx.feed_type or 'غير معروف'}
{price_line}
مؤشرات H1 (زخم لحظي): RSI {_fmt(ctx.rsi, 1)} | MACD {_fmt(ctx.macd, 4)} | ADX {_fmt(ctx.adx, 1)}
EMA9/21 (قصير): {_fmt(ctx.ema_9)} / {_fmt(ctx.ema_21)}
نظام السوق H1: {ctx.regime or 'N/A'}
قرار الوكلاء: {ctx.agent_direction or 'N/A'} (ثقة: {_fmt(ctx.agent_confidence, 2) if ctx.agent_confidence else 'N/A'})
آخر إشارة APEX: {ctx.latest_signal_direction or 'لا إشارة'}
اكتمال البيانات: {'نعم' if ctx.data_complete else 'لا — بيانات APEX غير متوفرة'}
"""
        blocks.append(block.strip())
    return "\n\n".join(blocks)


async def _build_user_prompt(
    message: str,
    contexts: list[AdvisorAssetContext],
    focus_symbol: str | None,
) -> str:
    focus_line = f"\nالأصل المطلوب التركيز عليه: {focus_symbol}\n" if focus_symbol else ""
    ctx_by_sym = {c.symbol: c for c in contexts}
    target_symbols = [focus_symbol] if focus_symbol else [c.symbol for c in contexts]

    intraday_sections: list[str] = []
    for sym in target_symbols:
        ctx = ctx_by_sym.get(sym)
        if ctx:
            block = await _build_intraday_block(sym, ctx)
            intraday_sections.append(f"=== سياق لحظي {sym} ===\n{block}")

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    apex_json = json.dumps([c.model_dump(mode="json") for c in contexts], ensure_ascii=False, indent=2)
    return f"""{focus_line}
--- تعليمات هذا الطلب ---
الوقت: {now_utc}
الأفق الزمني: 15–60 دقيقة فقط (تداول لحظي H1)
تجاهل: أي توقع يومي/أسبوعي/شهري
الدخول: ضمن ±0.5% من سعر APEX الحالي
SL/TP: واقعيان لـ H1 (قريبان — ليس بعيدين)
مصدر البيانات: APEX الداخلي فقط — لا مصادر خارجية

--- بيانات APEX (JSON) ---
{apex_json}

--- ملخص APEX ---
{_format_apex_context(contexts)}

--- سياق لحظي: شموع H1 + أنماط + زخم + نطاق الدخول ---
{chr(10).join(intraday_sections) if intraday_sections else "لا سياق لحظي"}

--- سؤال المستخدم ---
{message}
"""


def _apex_data_available(contexts: list[AdvisorAssetContext], focus_symbol: str | None) -> bool:
    if focus_symbol:
        ctx = next((c for c in contexts if c.symbol == focus_symbol), None)
        return bool(ctx and ctx.data_complete)
    return any(c.data_complete for c in contexts)


async def get_advisor_context() -> AdvisorContextResponse:
    contexts = await build_all_advisor_context()
    return AdvisorContextResponse(
        assets=contexts,
        timestamp=datetime.now(timezone.utc),
    )


async def advisor_chat(
    message: str,
    *,
    symbol: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> AdvisorChatResponse:
    if symbol and symbol not in ACTIVE_SYMBOLS:
        raise ValueError(f"Unknown symbol: {symbol}")

    if not llm_client.is_configured:
        raise LLMClientError("OpenAI API key not configured")

    contexts = await build_all_advisor_context()

    if not _apex_data_available(contexts, symbol):
        logger.info("advisor_chat_data_unavailable", symbol=symbol)
        return AdvisorChatResponse(
            reply=DATA_UNAVAILABLE_MSG,
            symbol=symbol,
            model=llm_client.model,
            latency_ms=0.0,
            web_search_used=False,
            apex_context=contexts,
            timestamp=datetime.now(timezone.utc),
        )

    user_prompt = await _build_user_prompt(message, contexts, symbol)

    conv_history = [{"role": m["role"], "content": m["content"]} for m in (history or [])][-10:]

    response = await llm_client.advisor_chat(
        ADVISOR_SYSTEM_PROMPT,
        user_prompt,
        conversation_history=conv_history,
    )

    reply = _ensure_intraday_disclaimer(response.content)

    logger.info(
        "advisor_chat_complete",
        symbol=symbol,
        latency_ms=round(response.latency_ms, 1),
    )

    return AdvisorChatResponse(
        reply=reply,
        symbol=symbol,
        model=response.model,
        latency_ms=response.latency_ms,
        web_search_used=False,
        apex_context=contexts,
        timestamp=datetime.now(timezone.utc),
    )
