"""Bootstrap XAUUSD H1 history into PostgreSQL (target: 500 bars)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.feeds.history_bootstrap import XAUUSD_BOOTSTRAP_BARS, bootstrap_asset
from app.services.market_data_store import count_bars_in_db, get_oldest_bar_timestamp


async def main() -> None:
    ok = await bootstrap_asset("XAUUSD", limit=XAUUSD_BOOTSTRAP_BARS)
    total = await count_bars_in_db("XAUUSD")
    oldest = await get_oldest_bar_timestamp("XAUUSD")
    print("=== XAUUSD Bootstrap ===")
    print(f"  success:     {ok}")
    print(f"  target:      {XAUUSD_BOOTSTRAP_BARS}")
    print(f"  db_count:    {total}")
    print(f"  oldest_bar:  {oldest.isoformat() if oldest else 'N/A'}")
    if total < XAUUSD_BOOTSTRAP_BARS:
        print(f"  STATUS: INCOMPLETE ({total}/{XAUUSD_BOOTSTRAP_BARS})")
        sys.exit(1)
    print("  STATUS: OK")


if __name__ == "__main__":
    asyncio.run(main())
