"""XAUUSD pre-market readiness checks."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.config.assets import ASSETS
from app.engines.indicator_engine import OHLCVBar
from app.engines.signal_generator import SignalGenerator
from app.schemas import RegimeSnapshotSchema, RegimeType, SignalDirection
from app.services.market_hours import is_market_open, next_market_open
from app.services.market_status_service import build_market_status
from app.services.pipeline import process_bar

BAGHDAD = ZoneInfo("Asia/Baghdad")


def _iraq(y, m, d, h, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=BAGHDAD).astimezone(timezone.utc)


def test_xauusd_h1_config() -> None:
    asset = ASSETS["XAUUSD"]
    assert asset.candle_interval == "1h"
    assert asset.feed_type == "twelvedata"
    assert asset.min_price_move == 0.50
    assert asset.default_spread == 0.30
    assert settings.min_signal_confidence_pct == 75.0
    assert settings.min_risk_reward_ratio == 2.0
    assert settings.signal_cooldown_hours == 1.0


def test_xauusd_entry_zone() -> None:
    gen = SignalGenerator()
    low, high, center = gen._entry_zone("XAUUSD", 2700.0)
    assert low == 2693.25
    assert high == 2706.75
    assert center == 2700.0
    low_btc, high_btc, center_btc = gen._entry_zone("BTCUSDT", 95000.0)
    assert center_btc == 95000.0
    assert low_btc < center_btc < high_btc


def test_xauusd_closed_on_saturday() -> None:
    sat = _iraq(2026, 5, 30, 12)
    assert is_market_open("XAUUSD", sat) is False


def test_xauusd_opens_monday_1am_iraq() -> None:
    mon_open = _iraq(2026, 6, 1, 1, 0)
    assert is_market_open("XAUUSD", mon_open) is True


def test_xauusd_next_open_from_saturday_is_monday_1am() -> None:
    sat = _iraq(2026, 5, 30, 20)
    nxt = next_market_open("XAUUSD", sat)
    assert nxt is not None
    local = nxt.astimezone(BAGHDAD)
    assert local.weekday() == 0
    assert local.hour == 1
    assert local.minute == 0


@pytest.mark.asyncio
async def test_xauusd_market_status_shows_closed_with_countdown() -> None:
    sat = _iraq(2026, 5, 30, 20)
    status = await build_market_status("XAUUSD", sat)
    assert status.is_open is False
    assert status.next_open_at is not None
    assert status.seconds_until_open is not None
    assert status.seconds_until_open > 0


@pytest.mark.asyncio
async def test_pipeline_skips_gold_when_market_closed() -> None:
    bar = {
        "symbol": "XAUUSD",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "open": 2700.0,
        "high": 2701.0,
        "low": 2699.0,
        "close": 2700.5,
        "volume": 100.0,
        "source": "twelvedata",
        "is_closed": True,
    }
    with patch("app.services.pipeline.is_market_open", return_value=False):
        with patch("app.services.pipeline.build_market_status", new_callable=AsyncMock) as mock_status:
            with patch("app.services.pipeline.build_asset_dashboard_state", new_callable=AsyncMock) as mock_dash:
                mock_state = MagicMock()
                mock_state.model_dump.return_value = {"symbol": "XAUUSD"}
                mock_dash.return_value = mock_state
                with patch("app.services.pipeline.set_dashboard_state", new_callable=AsyncMock):
                    with patch("app.services.pipeline.broadcaster") as mock_bc:
                        mock_bc.broadcast_dashboard_update = AsyncMock()
                        mock_bc.broadcast_market_status = AsyncMock()
                        await process_bar(bar)
                        mock_status.assert_awaited_once()
                        mock_bc.broadcast_price.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_runs_gold_even_when_market_closed() -> None:
    from app.feeds.history_bootstrap import bootstrap_asset

    bars = [{"symbol": "XAUUSD", "timestamp": "2026-06-01T12:00:00+00:00", "close": 4400.0}] * 200
    with patch("app.services.market_hours.is_market_open", return_value=False):
        with patch(
            "app.feeds.history_bootstrap.fetch_bootstrap_history",
            new=AsyncMock(return_value=bars),
        ):
            with patch(
                "app.services.market_data_store.persist_bars_batch",
                new=AsyncMock(return_value=200),
            ):
                with patch("app.services.pipeline.seed_bars_to_buffer"):
                    with patch("app.services.pipeline.process_bar", new=AsyncMock()):
                        with patch(
                            "app.feeds.history_bootstrap._mark_feed_warmed",
                            new=AsyncMock(),
                        ):
                            ok = await bootstrap_asset("XAUUSD")
    assert ok is True


def test_signal_generator_rejects_low_confidence() -> None:
    gen = SignalGenerator()
    now = datetime.now(timezone.utc)
    bars = [
        OHLCVBar(
            timestamp=now,
            open=2700.0,
            high=2701.0,
            low=2699.0,
            close=2700.0,
            volume=100.0,
        )
    ]
    indicators = gen.indicator_engine.compute(bars * 60, "XAUUSD")
    assert indicators is not None
    regime = RegimeSnapshotSchema(
        symbol="XAUUSD",
        timestamp=now,
        regime=RegimeType.RANGING,
        confidence=0.5,
    )
    signal, _ = gen.build_trading_signal(
        bars * 60,
        "XAUUSD",
        SignalDirection.LONG,
        0.50,
        indicators,
        regime,
        require_min_confidence=True,
    )
    assert signal is None
