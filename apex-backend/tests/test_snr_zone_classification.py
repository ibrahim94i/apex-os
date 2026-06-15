"""SNR zone classification — price vs level bands (±0.25%)."""

from datetime import datetime, timedelta, timezone

from app.engines.final_decision_engine import (
    apply_final_decision_to_consensus,
    classify_snr_state,
    resolve_snr_evaluation_price,
)
from app.engines.indicator_engine import OHLCVBar
from app.engines.snr_engine import SNREngine
from app.schemas.agent import AgentConsensus
from app.schemas.enums import SignalDirection
from app.schemas.snr import SNRSnapshotSchema
from app.utils.price_zones import level_zone_bounds, price_in_level_zone


def _bar(close: float, ts: datetime | None = None) -> OHLCVBar:
    t = ts or datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
    return OHLCVBar(timestamp=t, open=close, high=close + 1, low=close - 1, close=close, volume=1.0)


def _xauusd_snr(*, price: float) -> SNRSnapshotSchema:
    """Reproduce reported bug: price 4311 between S2 zone and S1 zone."""
    engine = SNREngine()
    s1, s2 = 4332.0, 4186.0
    return SNRSnapshotSchema(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        price=price,
        support_1=s1,
        support_2=s2,
        support_1_zone=engine._make_zone(s1),
        support_2_zone=engine._make_zone(s2),
    )


def test_price_outside_all_zones_is_normal_even_when_snapshot_price_stale() -> None:
    """Live price 4311 outside S1/S2 bands must not inherit stale snr.price inside zone."""
    snr = _xauusd_snr(price=4332.0)
    bars = [_bar(4311.0)]

    assert price_in_level_zone(4311.0, 4332.0) is False
    assert price_in_level_zone(4311.0, 4186.0) is False
    assert classify_snr_state(bars, snr, current_price=4311.0) == "NORMAL"
    assert resolve_snr_evaluation_price(bars, snr, current_price=4311.0) == 4311.0


def test_stale_snapshot_price_alone_must_not_force_inside_zone() -> None:
    snr = _xauusd_snr(price=4332.0)
    bars = [_bar(4311.0)]
    assert classify_snr_state(bars, snr) == "NORMAL"


def test_inside_zone_when_price_within_level_band() -> None:
    s1 = 4332.0
    price = 4332.0
    snr = _xauusd_snr(price=price)
    assert classify_snr_state([_bar(price)], snr, current_price=price) == "INSIDE_ZONE"


def test_zone_edge_outside_band_but_near_boundary() -> None:
    s1 = 4332.0
    s1_low, _ = level_zone_bounds(s1)
    price = s1_low * 0.9995
    snr = _xauusd_snr(price=price)
    assert classify_snr_state([_bar(price)], snr, current_price=price) == "ZONE_EDGE"


def test_breakout_confirmed_bullish_above_r1_zone() -> None:
    r1 = 4332.0
    _, r1_high = level_zone_bounds(r1)
    engine = SNREngine()
    snr = SNRSnapshotSchema(
        symbol="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        price=r1_high + 2.0,
        resistance_1=r1,
        resistance_1_zone=engine._make_zone(r1),
    )
    base = datetime(2026, 6, 4, tzinfo=timezone.utc)
    bars = [
        _bar(r1_high + 0.5, base),
        _bar(r1_high + 1.5, base + timedelta(hours=1)),
    ]
    assert classify_snr_state(bars, snr, current_price=bars[-1].close) == "BREAKOUT_CONFIRMED"


def test_snr_engine_price_in_level_zone_uses_levels_not_stale_zone_objects() -> None:
    engine = SNREngine()
    s1 = 4332.0
    snr = _xauusd_snr(price=4332.0)
    stale_zone = engine._make_zone(4200.0)
    snr = snr.model_copy(update={"support_1_zone": stale_zone})

    in_zone, reason, label = SNREngine._price_in_level_zone(4311.0, snr)
    assert in_zone is False
    assert reason is None
    assert label is None

    in_zone, reason, label = SNREngine._price_in_level_zone(4332.0, snr)
    assert in_zone is True
    assert reason == "snr_in_s1_zone"
    assert label == "S1"


def test_apply_final_decision_normal_when_price_between_zones() -> None:
    snr = _xauusd_snr(price=4332.0)
    consensus = apply_final_decision_to_consensus(
        AgentConsensus(
            symbol="XAUUSD",
            timestamp=datetime.now(timezone.utc),
            final_direction=SignalDirection.LONG,
            final_confidence=0.80,
            verdicts=[],
            vote_scores={},
        ),
        bars=[_bar(4311.0)],
        snr=snr,
        current_price=4311.0,
    )
    assert consensus.snr_state == "NORMAL"
    assert consensus.snr_warning_ar is None
    assert consensus.proposed_confidence == 0.80
