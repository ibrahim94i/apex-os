"""Phase 1 — decision path reads price_bars from DB only."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engines.indicator_engine import OHLCVBar
from app.services.pipeline import compute_snr_for_symbol, fetch_decision_bars, process_bar


def _bar(close: float, offset_hours: int) -> OHLCVBar:
    return OHLCVBar(
        timestamp=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc) + timedelta(hours=offset_hours),
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=100.0,
    )


@pytest.mark.asyncio
async def test_fetch_decision_bars_reads_agent_bars_from_db() -> None:
    raw = [
        {
            "symbol": "XAUUSD",
            "timestamp": "2026-06-17T10:00:00+00:00",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 10.0,
            "source": "metatrader",
        }
    ]
    with patch(
        "app.services.market_data_store.fetch_agent_bars_from_db",
        new=AsyncMock(return_value=raw),
    ) as mock_fetch:
        bars = await fetch_decision_bars("XAUUSD", limit=250)
    mock_fetch.assert_awaited_once_with("XAUUSD", limit=250, session=None)
    assert len(bars) == 1
    assert bars[0].close == 1.5


@pytest.mark.asyncio
async def test_compute_snr_for_decision_uses_db_close_not_redis() -> None:
    bars = [_bar(4320.0, h) for h in range(10)]
    with patch(
        "app.services.pipeline.fetch_decision_bars",
        new=AsyncMock(return_value=bars),
    ):
        with patch("app.core.cache.get_latest_price", new=AsyncMock()) as mock_price:
            snr = await compute_snr_for_symbol("XAUUSD")
    mock_price.assert_not_called()
    assert snr is not None
    assert snr.price == bars[-1].close


@pytest.mark.asyncio
async def test_compute_snr_for_display_can_use_redis_price() -> None:
    bars = [_bar(4320.0, h) for h in range(10)]
    with patch(
        "app.services.pipeline.fetch_decision_bars",
        new=AsyncMock(return_value=bars),
    ):
        with patch(
            "app.core.cache.get_latest_price",
            new=AsyncMock(return_value={"price": 9999.0}),
        ):
            snr = await compute_snr_for_symbol("XAUUSD", use_live_price=True)
    assert snr is not None
    assert snr.price == 9999.0


@pytest.mark.asyncio
async def test_process_bar_analyzes_db_decision_bars() -> None:
    decision_bars = [_bar(4300.0 + i, i) for i in range(200)]
    raw_bar = {
        "symbol": "XAUUSD",
        "timestamp": "2026-06-17T12:00:00+00:00",
        "open": 4310.0,
        "high": 4315.0,
        "low": 4305.0,
        "close": 4312.0,
        "volume": 100.0,
        "source": "metatrader",
        "is_closed": True,
    }

    mock_session = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.pipeline.AsyncSessionLocal", return_value=mock_cm):
        with patch("app.services.pipeline._persist_bar", new=AsyncMock()):
            with patch(
                "app.services.pipeline.fetch_decision_bars",
                new=AsyncMock(return_value=decision_bars),
            ) as mock_fetch:
                with patch(
                    "app.services.pipeline.should_run_h1_pipeline",
                    new=AsyncMock(return_value=False),
                ):
                    with patch("app.services.pipeline.signal_generator") as mock_gen:
                        mock_gen.analyze.return_value = (None, None)
                        with patch(
                            "app.services.pipeline.compute_snr_for_symbol",
                            new=AsyncMock(return_value=None),
                        ):
                            with patch(
                                "app.services.pipeline.build_asset_dashboard_state",
                                new=AsyncMock(),
                            ):
                                with patch(
                                    "app.services.pipeline.build_market_status",
                                    new=AsyncMock(return_value=None),
                                ):
                                    with patch(
                                        "app.services.pipeline.kill_switch"
                                    ) as mock_ks:
                                        mock_ks.load_from_cache = AsyncMock()
                                        mock_ks.evaluate = AsyncMock(
                                            return_value=MagicMock(model_dump=lambda **k: {})
                                        )
                                        await process_bar(raw_bar)

    mock_fetch.assert_awaited()
    analyze_bars = mock_gen.analyze.call_args.args[0]
    assert analyze_bars is decision_bars
