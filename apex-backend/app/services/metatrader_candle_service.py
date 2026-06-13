"""MetaTrader H1 candle ingest — PostgreSQL primary for XAUUSD when connected."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.core.cache import set_latest_price, set_metatrader_candle_state
from app.logging_config import logger
from app.services.market_data_store import upsert_metatrader_bar
from app.services.pipeline import process_bar
from app.utils.time_utils import compute_age_seconds, parse_utc_timestamp


def _candle_stale_seconds() -> int:
    return max(settings.metatrader_candle_stale_seconds, 3600)


async def is_metatrader_candles_connected(symbol: str, raw: dict[str, Any] | None = None) -> bool:
    from app.core.cache import get_metatrader_candle_state

    data = raw if raw is not None else await get_metatrader_candle_state(symbol)
    if not data:
        return False
    ts_raw = data.get("last_candle_at") or data.get("received_at")
    if not ts_raw:
        return False
    age = compute_age_seconds(parse_utc_timestamp(str(ts_raw)))
    return age <= _candle_stale_seconds()


async def ingest_metatrader_candle(parsed: dict[str, Any]) -> dict[str, Any]:
    """Persist H1 candle, update cache, and run analysis pipeline."""
    symbol = parsed["symbol"]
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

    await upsert_metatrader_bar(bar)
    await set_metatrader_candle_state(
        symbol,
        {
            "symbol": symbol,
            "last_candle_at": bar_timestamp.isoformat(),
            "received_at": received_at.isoformat(),
            "close_time": parsed["close_time"].isoformat(),
            "source": "metatrader",
        },
    )
    await set_latest_price(symbol, float(parsed["close"]), bar_timestamp.isoformat())

    pipeline_ran = False
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

    logger.info(
        "metatrader_candle_ingested",
        symbol=symbol,
        timestamp=bar_timestamp.isoformat(),
        close=parsed["close"],
        pipeline_ran=pipeline_ran,
    )

    return {
        "symbol": symbol,
        "timeframe": parsed["timeframe"],
        "timestamp": bar_timestamp.isoformat(),
        "received_at": received_at.isoformat(),
        "pipeline_ran": pipeline_ran,
    }
