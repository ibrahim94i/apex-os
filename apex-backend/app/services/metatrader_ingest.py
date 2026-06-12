"""MetaTrader request parsing and auth — tolerant of MT4 WebRequest payloads."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.logging_config import logger

MT_AUTH_HEADER = "X-MT-Key"


def extract_mt_api_key(headers: dict[str, str]) -> str | None:
    """Read API key from X-MT-Key only (case-insensitive header lookup)."""
    for key, value in headers.items():
        if key.lower() == MT_AUTH_HEADER.lower():
            cleaned = (value or "").strip()
            return cleaned or None
    return None


def verify_metatrader_api_key(received_key: str | None) -> tuple[bool, str | None]:
    """
    Validate against METATRADER_API_KEY.
    Returns (ok, error_detail).
    """
    expected = (settings.metatrader_api_key or "").strip()
    if not expected:
        return False, "MetaTrader API key not configured on server (METATRADER_API_KEY)"
    received = (received_key or "").strip()
    if not received:
        return False, "Missing X-MT-Key header"
    if received != expected:
        return False, "Invalid X-MT-Key"
    return True, None


def _coerce_float(value: Any, field: str) -> float:
    if value is None:
        raise ValueError(f"missing {field}")
    if isinstance(value, str):
        value = value.strip().replace(",", "")
    number = float(value)
    if number <= 0:
        raise ValueError(f"{field} must be > 0")
    return number


def _parse_time(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return datetime.now(timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = text.replace(".", "-", 2) if re.match(r"^\d{4}\.\d{2}\.\d{2}", text) else text
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(f"invalid time format: {value}") from exc


def _normalize_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


def parse_metatrader_request_body(raw_body: bytes) -> dict[str, Any]:
    """Parse MT4/MT5 JSON body with flexible types for bid/ask/time."""
    if not raw_body:
        raise ValueError("empty request body")

    text = _normalize_json_text(raw_body.decode("utf-8", errors="replace"))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON body: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")

    symbol_raw = payload.get("symbol") or payload.get("Symbol")
    if not symbol_raw:
        raise ValueError("missing symbol")

    bid_raw = payload.get("bid", payload.get("Bid"))
    ask_raw = payload.get("ask", payload.get("Ask"))
    time_raw = payload.get("time", payload.get("Time", payload.get("timestamp")))

    symbol = str(symbol_raw).strip().upper()
    bid = _coerce_float(bid_raw, "bid")
    ask = _coerce_float(ask_raw, "ask")
    if ask < bid:
        raise ValueError("ask must be >= bid")

    quote_time = _parse_time(time_raw)
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "time": quote_time,
    }


def sanitize_headers_for_log(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() == MT_AUTH_HEADER.lower():
            out[key] = value
        elif key.lower() in {"content-type", "user-agent", "host", "content-length"}:
            out[key] = value
    return out
