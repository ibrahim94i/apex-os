"""MetaTrader candle ingest — H1 drives pipeline; other TFs stored for charts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.core.cache import set_latest_price, set_metatrader_candle_state
from app.logging_config import logger
from app.services.market_data_store import (
    bootstrap_metatrader_h1_bars,
    upsert_chart_bar,
    upsert_metatrader_bar,
)
from app.services.pipeline import process_bar
from app.utils.time_utils import compute_age_seconds, parse_utc_timestamp

CHART_TIMEFRAMES: frozenset[str] = frozenset({"M5", "M15", "H4", "D1"})

CHART_STALE_SECONDS: dict[str, int] = {
    "M5": 900,
    "M15": 2700,
    "H4": 18000,
    "D1": 172800,
}


def _h1_stale_seconds() -> int:
    return max(settings.metatrader_candle_stale_seconds, 3600)


def _chart_stale_seconds(timeframe: str) -> int:
    return CHART_STALE_SECONDS.get(timeframe, settings.metatrader_candle_stale_seconds)


async def is_metatrader_candles_connected(symbol: str, raw: dict[str, Any] | None = None) -> bool:
    from app.core.cache import get_metatrader_candle_state

    data = raw if raw is not None else await get_metatrader_candle_state(symbol)
    if not data:
        return False
    ts_raw = data.get("last_candle_at") or data.get("received_at")
    if not ts_raw:
        return False
    age = compute_age_seconds(parse_utc_timestamp(str(ts_raw)))
    return age <= _h1_stale_seconds()


async def is_metatrader_chart_timeframe_connected(
    symbol: str,
    timeframe: str,
    raw: dict[str, Any] | None = None,
) -> bool:
    from app.core.cache import get_metatrader_candle_state

    if timeframe == "H1":
        return await is_metatrader_candles_connected(symbol, raw)

    data = raw if raw is not None else await get_metatrader_candle_state(symbol)
    if not data:
        return False

    tf_state = (data.get("timeframes") or {}).get(timeframe)
    if not isinstance(tf_state, dict):
        return False

    ts_raw = tf_state.get("last_candle_at") or tf_state.get("received_at")
    if not ts_raw:
        return False
    age = compute_age_seconds(parse_utc_timestamp(str(ts_raw)))
    return age <= _chart_stale_seconds(timeframe)


async def ingest_metatrader_candle(parsed: dict[str, Any]) -> dict[str, Any]:
    """Persist candle, update cache, and run H1 analysis pipeline when applicable."""
    symbol = parsed["symbol"]
    timeframe = parsed["timeframe"]
    received_at = datetime.now(timezone.utc)
    bar_timestamp = parsed["timestamp"]
    if bar_timestamp.tzinfo is None:
        bar_timestamp = bar_timestamp.replace(tzinfo=timezone.utc)

    bar = {
        "symbol": symbol,
        "timestamp": bar_timestamp.isoformat(),
        "open": parsed["open"],
        "high": parsed["high"],
        "low": parsed["low"],
        "close": parsed["close"],
        "volume": parsed["volume"],
        "source": "metatrader",
        "is_closed": True,
    }

    pipeline_ran = False
    if timeframe == "H1":
        await upsert_metatrader_bar(bar)
        await set_latest_price(symbol, float(parsed["close"]), bar_timestamp.isoformat())
        try:
            await process_bar(bar)
            pipeline_ran = True
        except Exception as exc:
            logger.error(
                "metatrader_candle_pipeline_failed",
                symbol=symbol,
                timestamp=bar_timestamp.isoformat(),
                error=str(exc),
            )
    else:
        await upsert_chart_bar(timeframe, bar)

    from app.core.cache import get_metatrader_candle_state

    existing = await get_metatrader_candle_state(symbol) or {}
    timeframes = dict(existing.get("timeframes") or {})
    tf_payload = {
        "last_candle_at": bar_timestamp.isoformat(),
        "received_at": received_at.isoformat(),
        "close_time": parsed["close_time"].isoformat(),
        "source": "metatrader",
    }
    timeframes[timeframe] = tf_payload

    state: dict[str, Any] = {
        "symbol": symbol,
        "received_at": received_at.isoformat(),
        "source": "metatrader",
        "timeframes": timeframes,
    }
    if timeframe == "H1":
        state["last_candle_at"] = bar_timestamp.isoformat()
        state["close_time"] = parsed["close_time"].isoformat()

    await set_metatrader_candle_state(symbol, state)

    logger.info(
        "metatrader_candle_ingested",
        symbol=symbol,
        timeframe=timeframe,
        timestamp=bar_timestamp.isoformat(),
        close=parsed["close"],
        pipeline_ran=pipeline_ran,
    )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "timestamp": bar_timestamp.isoformat(),
        "received_at": received_at.isoformat(),
        "pipeline_ran": pipeline_ran,
    }


async def ingest_metatrader_h1_bootstrap(parsed: dict[str, Any]) -> dict[str, Any]:
    """Persist historical H1 batch and replace Binance bars in the same window."""
    symbol = parsed["symbol"]
    bars = parsed["bars"]
    received_at = datetime.now(timezone.utc)

    result = await bootstrap_metatrader_h1_bars(symbol, bars)
    newest = bars[-1]
    newest_ts = newest["timestamp"]
    if newest_ts.tzinfo is None:
        newest_ts = newest_ts.replace(tzinfo=timezone.utc)

    from app.core.cache import get_metatrader_candle_state

    existing = await get_metatrader_candle_state(symbol) or {}
    timeframes = dict(existing.get("timeframes") or {})
    tf_payload = {
        "last_candle_at": newest_ts.isoformat(),
        "received_at": received_at.isoformat(),
        "close_time": newest["close_time"].isoformat(),
        "source": "metatrader",
        "bootstrapped": True,
        "bootstrap_count": len(bars),
    }
    timeframes["H1"] = tf_payload

    await set_metatrader_candle_state(
        symbol,
        {
            "symbol": symbol,
            "received_at": received_at.isoformat(),
            "source": "metatrader",
            "last_candle_at": newest_ts.isoformat(),
            "close_time": newest["close_time"].isoformat(),
            "bootstrapped_at": received_at.isoformat(),
            "bootstrap_count": len(bars),
            "timeframes": timeframes,
        },
    )
    await set_latest_price(symbol, float(newest["close"]), newest_ts.isoformat())

    logger.info(
        "metatrader_h1_bootstrap_ingested",
        symbol=symbol,
        upserted=result["upserted"],
        deleted=result["deleted"],
        oldest=result["oldest"],
        newest=result["newest"],
    )

    return {
        "symbol": symbol,
        "timeframe": "H1",
        "received_at": received_at.isoformat(),
        **result,
    }
