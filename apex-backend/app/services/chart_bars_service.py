"""Chart-only OHLCV bars — does not affect agent pipeline (agents stay on H1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx

from app.config import settings
from app.config.assets import get_asset
from app.feeds.history_bootstrap import _finalize_bar, _normalize_bar
from app.feeds.twelvedata_limiter import can_afford_credits, throttled_get
from app.logging_config import logger
from app.services.market_data_store import fetch_bars_from_db

ChartTimeframe = Literal["M5", "M15", "H1", "H4", "D1"]
ChartDataSource = Literal["db", "twelvedata", "resampled"]

CHART_TIMEFRAMES: dict[str, str] = {
    "M5": "5min",
    "M15": "15min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}

DEFAULT_CHART_TIMEFRAME: ChartTimeframe = "H1"
AGENT_TIMEFRAME = "H1"
_RESAMPLE_DB_LIMIT = 500

TWELVEDATA_URL = "https://api.twelvedata.com/time_series"


def normalize_chart_timeframe(value: str) -> ChartTimeframe:
    code = value.strip().upper()
    if code not in CHART_TIMEFRAMES:
        raise ValueError(f"Unsupported chart timeframe: {value}")
    return code  # type: ignore[return-value]


def _parse_bar_timestamp(bar: dict[str, Any]) -> datetime:
    ts = bar["timestamp"]
    if isinstance(ts, datetime):
        dt = ts
    else:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _clone_bar(bar: dict[str, Any], *, timestamp: datetime, source: str) -> dict[str, Any]:
    return {
        **bar,
        "timestamp": timestamp.isoformat(),
        "source": source,
        "is_closed": True,
    }


def _merge_bar_group(group: list[dict[str, Any]], bucket_start: datetime, source: str) -> dict[str, Any]:
    return {
        "symbol": group[0]["symbol"],
        "timestamp": bucket_start.isoformat(),
        "open": float(group[0]["open"]),
        "high": max(float(b["high"]) for b in group),
        "low": min(float(b["low"]) for b in group),
        "close": float(group[-1]["close"]),
        "volume": sum(float(b.get("volume", 0.0)) for b in group),
        "source": source,
        "is_closed": True,
    }


def _expand_h1_bar(bar: dict[str, Any], *, minutes: int, slots: int) -> list[dict[str, Any]]:
    start = _parse_bar_timestamp(bar).replace(minute=0, second=0, microsecond=0)
    return [
        _clone_bar(
            bar,
            timestamp=start + timedelta(minutes=minutes * slot),
            source="resampled",
        )
        for slot in range(slots)
    ]


def _aggregate_fixed_hours(bars: list[dict[str, Any]], hours: int) -> list[dict[str, Any]]:
    if not bars:
        return []
    period_sec = hours * 3600
    buckets: dict[int, list[dict[str, Any]]] = {}
    for bar in bars:
        ts = _parse_bar_timestamp(bar)
        bucket_key = int(ts.timestamp()) // period_sec
        buckets.setdefault(bucket_key, []).append(bar)

    merged: list[dict[str, Any]] = []
    for bucket_key in sorted(buckets):
        group = buckets[bucket_key]
        bucket_start = datetime.fromtimestamp(bucket_key * period_sec, tz=timezone.utc)
        merged.append(_merge_bar_group(group, bucket_start, "resampled"))
    return merged


def _aggregate_daily(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not bars:
        return []
    buckets: dict[str, list[dict[str, Any]]] = {}
    for bar in bars:
        ts = _parse_bar_timestamp(bar)
        day_key = ts.date().isoformat()
        buckets.setdefault(day_key, []).append(bar)

    merged: list[dict[str, Any]] = []
    for day_key in sorted(buckets):
        group = buckets[day_key]
        day_start = _parse_bar_timestamp(group[0]).replace(hour=0, minute=0, second=0, microsecond=0)
        merged.append(_merge_bar_group(group, day_start, "resampled"))
    return merged


def resample_h1_bars_for_chart(
    h1_bars: list[dict[str, Any]],
    timeframe: ChartTimeframe,
) -> list[dict[str, Any]]:
    """Build display-only candles from stored H1 history when TwelveData is unavailable."""
    if timeframe == "H1" or not h1_bars:
        return h1_bars

    if timeframe == "M5":
        expanded: list[dict[str, Any]] = []
        for bar in h1_bars:
            expanded.extend(_expand_h1_bar(bar, minutes=5, slots=12))
        return expanded

    if timeframe == "M15":
        expanded = []
        for bar in h1_bars:
            expanded.extend(_expand_h1_bar(bar, minutes=15, slots=4))
        return expanded

    if timeframe == "H4":
        return _aggregate_fixed_hours(h1_bars, 4)

    if timeframe == "D1":
        return _aggregate_daily(h1_bars)

    return h1_bars


def _parse_twelvedata_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unsupported TwelveData datetime: {value}")


async def _fetch_twelvedata_chart_series(
    *,
    td_symbol: str,
    apex_symbol: str,
    interval: str,
    limit: int,
) -> list[dict[str, Any]]:
    api_key = settings.twelvedata_api_key
    if not api_key or api_key == "your_key_here":
        return []

    if not await can_afford_credits(limit):
        logger.warning("chart_bars_skipped_credits", symbol=apex_symbol, interval=interval)
        return []

    params = {
        "symbol": td_symbol,
        "interval": interval,
        "outputsize": limit,
        "apikey": api_key,
    }

    data: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(1, 4):
            response = await throttled_get(
                client,
                TWELVEDATA_URL,
                params=params,
                reason="chart_view",
            )
            if response.status_code == 429:
                await asyncio.sleep(15.0 * attempt)
                continue
            if response.status_code == 404:
                logger.warning(
                    "chart_bars_interval_unavailable",
                    symbol=apex_symbol,
                    interval=interval,
                )
                return []
            response.raise_for_status()
            data = response.json()
            break

    if not data or "values" not in data or not data["values"]:
        return []

    bars: list[dict[str, Any]] = []
    for row in reversed(data["values"]):
        ts = _parse_twelvedata_datetime(str(row["datetime"]))
        bars.append(
            _finalize_bar(
                _normalize_bar(
                    symbol=apex_symbol,
                    timestamp=ts,
                    open_=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                    source="twelvedata",
                )
            )
        )
    return bars


async def fetch_chart_bars(
    symbol: str,
    *,
    interval: str = DEFAULT_CHART_TIMEFRAME,
    limit: int = 200,
) -> tuple[list[dict[str, Any]], ChartTimeframe, ChartDataSource]:
    """Return bars for dashboard chart display only."""
    timeframe = normalize_chart_timeframe(interval)
    capped_limit = min(max(limit, 1), 500)

    h1_bars = await fetch_bars_from_db(symbol, _RESAMPLE_DB_LIMIT)

    if timeframe == "H1":
        return h1_bars[-capped_limit:], timeframe, "db"

    asset = get_asset(symbol)
    if asset and asset.feed_type == "twelvedata" and asset.twelvedata_symbol:
        bars = await _fetch_twelvedata_chart_series(
            td_symbol=asset.twelvedata_symbol,
            apex_symbol=symbol,
            interval=CHART_TIMEFRAMES[timeframe],
            limit=capped_limit,
        )
        if bars:
            return bars[-capped_limit:], timeframe, "twelvedata"

    resampled = resample_h1_bars_for_chart(h1_bars, timeframe)
    if not resampled:
        logger.warning("chart_bars_resample_empty", symbol=symbol, timeframe=timeframe)
        return h1_bars[-capped_limit:], "H1", "db"

    logger.info(
        "chart_bars_resampled_from_h1",
        symbol=symbol,
        timeframe=timeframe,
        h1_bars=len(h1_bars),
        resampled=len(resampled),
    )
    return resampled[-capped_limit:], timeframe, "resampled"
