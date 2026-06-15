"""MetaTrader candle request parsing — tolerant of MT4 WebRequest payloads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.metatrader_ingest import _coerce_float, _normalize_json_bytes, _parse_time

SUPPORTED_TIMEFRAMES: frozenset[str] = frozenset({"M5", "M15", "H1", "1H", "H4", "D1"})

_TIMEFRAME_ALIASES: dict[str, str] = {
    "1H": "H1",
}

_TIMEFRAME_DELTAS: dict[str, timedelta] = {
    "M5": timedelta(minutes=5),
    "M15": timedelta(minutes=15),
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
    "D1": timedelta(days=1),
}


def normalize_metatrader_timeframe(value: str) -> str:
    code = str(value).strip().upper()
    code = _TIMEFRAME_ALIASES.get(code, code)
    if code not in _TIMEFRAME_DELTAS:
        raise ValueError(f"unsupported timeframe: {value}")
    return code


def bar_open_from_close_time(close_time: datetime, timeframe: str) -> datetime:
    """Convert EA bar close time to canonical bar open timestamp."""
    tf = normalize_metatrader_timeframe(timeframe)
    bar_open = close_time - _TIMEFRAME_DELTAS[tf]
    if bar_open.tzinfo is None:
        bar_open = bar_open.replace(tzinfo=timezone.utc)

    if tf == "M5":
        minute = (bar_open.minute // 5) * 5
        return bar_open.replace(minute=minute, second=0, microsecond=0)
    if tf == "M15":
        minute = (bar_open.minute // 15) * 15
        return bar_open.replace(minute=minute, second=0, microsecond=0)
    if tf == "H1":
        return bar_open.replace(minute=0, second=0, microsecond=0)
    if tf == "H4":
        hour = (bar_open.hour // 4) * 4
        return bar_open.replace(hour=hour, minute=0, second=0, microsecond=0)
    if tf == "D1":
        return bar_open.replace(hour=0, minute=0, second=0, microsecond=0)
    return bar_open


def parse_metatrader_candle_body(raw_body: bytes) -> dict[str, Any]:
    """Parse MT4/MT5 OHLCV JSON body for M5/M15/H1/H4/D1."""
    import json

    if not raw_body:
        raise ValueError("empty request body")

    text = _normalize_json_bytes(raw_body)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON body: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")

    symbol_raw = payload.get("symbol") or payload.get("Symbol")
    if not symbol_raw:
        raise ValueError("missing symbol")

    timeframe_raw = payload.get("timeframe") or payload.get("Timeframe") or "H1"
    timeframe = normalize_metatrader_timeframe(str(timeframe_raw))

    open_ = _coerce_float(payload.get("open", payload.get("Open")), "open")
    high = _coerce_float(payload.get("high", payload.get("High")), "high")
    low = _coerce_float(payload.get("low", payload.get("Low")), "low")
    close = _coerce_float(payload.get("close", payload.get("Close")), "close")

    volume_raw = payload.get("volume", payload.get("Volume", 0))
    try:
        volume = float(volume_raw) if volume_raw is not None else 0.0
    except (TypeError, ValueError):
        volume = 0.0
    if volume < 0:
        volume = 0.0

    if high < low:
        raise ValueError("high must be >= low")
    if not (low <= open_ <= high and low <= close <= high):
        raise ValueError("open/close must be within high/low range")

    time_raw = payload.get("time", payload.get("Time", payload.get("timestamp")))
    event_time = _parse_time(time_raw)
    bar_open = bar_open_from_close_time(event_time, timeframe)

    return {
        "symbol": str(symbol_raw).strip().upper(),
        "timeframe": timeframe,
        "timestamp": bar_open,
        "close_time": event_time.astimezone(timezone.utc),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
