"""MetaTrader H1 candle request parsing — tolerant of MT4 WebRequest payloads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.metatrader_ingest import _coerce_float, _normalize_json_bytes, _parse_time


def parse_metatrader_candle_body(raw_body: bytes) -> dict[str, Any]:
    """Parse MT4/MT5 H1 OHLCV JSON body."""
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
    timeframe = str(timeframe_raw).strip().upper()
    if timeframe not in {"H1", "1H"}:
        raise ValueError(f"unsupported timeframe: {timeframe_raw}")

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

    # EA sends bar close time — store canonical H1 open time (matches Binance/DB key).
    bar_open = event_time - timedelta(hours=1)
    bar_open = bar_open.replace(minute=0, second=0, microsecond=0)
    if bar_open.tzinfo is None:
        bar_open = bar_open.replace(tzinfo=timezone.utc)

    return {
        "symbol": str(symbol_raw).strip().upper(),
        "timeframe": "H1",
        "timestamp": bar_open,
        "close_time": event_time.astimezone(timezone.utc),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
