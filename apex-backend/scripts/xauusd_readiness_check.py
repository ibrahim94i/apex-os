"""Run live XAUUSD readiness verification."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.config import settings
from app.config.assets import ASSETS
from app.database import AsyncSessionLocal
from app.models import TradingSignal
from app.services.market_hours import is_market_open, next_market_open
from app.services.market_status_service import build_market_status

BAGHDAD = ZoneInfo("Asia/Baghdad")


async def main() -> None:
    now = datetime.now(timezone.utc)
    local = now.astimezone(BAGHDAD)
    asset = ASSETS["XAUUSD"]
    open_now = is_market_open("XAUUSD", now)
    nxt = next_market_open("XAUUSD", now)
    status = await build_market_status("XAUUSD", now)

    async with AsyncSessionLocal() as session:
        sig_count = (
            await session.execute(
                select(func.count())
                .select_from(TradingSignal)
                .where(TradingSignal.symbol == "XAUUSD")
            )
        ).scalar_one()

    hours_until = (status.seconds_until_open or 0) // 3600
    mins_until = ((status.seconds_until_open or 0) % 3600) // 60

    print("=== XAUUSD Readiness Report ===")
    print(f"  Iraq time now:     {local.strftime('%A %Y-%m-%d %H:%M')}")
    print(f"  Market open:       {'YES' if open_now else 'NO'}")
    if not open_now and nxt:
        print(f"  Opens at:          {nxt.astimezone(BAGHDAD).strftime('%A %H:%M')} Iraq")
        print(f"  Countdown:         {hours_until}h {mins_until}m")
    print(f"  Timeframe:         {asset.candle_interval}")
    print(f"  Default spread:    {asset.default_spread}")
    print(f"  Min price move:    {asset.min_price_move}")
    print(f"  Min confidence:    {settings.min_signal_confidence_pct}%")
    print(f"  Min R:R:           1:{settings.min_risk_reward_ratio:.0f}")
    print(f"  DB gold signals:   {sig_count}")
    print(f"  TwelveData key:    {'configured' if settings.twelvedata_api_key else 'MISSING'}")
    print()

    checks = [
        asset.candle_interval == "1h",
        asset.default_spread == 0.30,
        asset.min_price_move == 0.50,
        settings.min_signal_confidence_pct >= 75.0,
        settings.min_risk_reward_ratio >= 2.0,
        sig_count == 0,
        settings.twelvedata_api_key not in ("", "your_key_here"),
    ]
    if not open_now:
        checks.extend(
            [
                status.is_open is False,
                status.next_open_at is not None,
                (status.seconds_until_open or 0) > 0,
            ]
        )

    passed = sum(checks)
    total = len(checks)
    print(f"  Checks passed: {passed}/{total}")
    if passed == total:
        print("  STATUS: READY")
    else:
        print("  STATUS: NEEDS ATTENTION")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
