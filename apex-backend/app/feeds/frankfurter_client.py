"""FX rate client facade — delegates to fx_rate_client provider chain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.feeds.fx_rate_client import (
    build_hourly_bar,
    fetch_historical_daily_bars,
    fetch_latest_rate,
    fetch_latest_rate_with_source,
)

__all__ = [
    "build_hourly_bar",
    "fetch_historical_daily_bars",
    "fetch_latest_rate",
    "fetch_latest_rate_with_source",
]
