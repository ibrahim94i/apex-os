"""Volume policy tests — XAUUSD volume is always ignored."""

from app.utils.volume_policy import apply_volume_policy, apply_volume_policy_to_bar, volume_is_reliable


def test_xauusd_volume_not_reliable() -> None:
    assert volume_is_reliable("XAUUSD") is False
    assert volume_is_reliable("BTCUSDT") is True


def test_xauusd_volume_forced_zero() -> None:
    assert apply_volume_policy("XAUUSD", 999.0) == 0.0
    bar = apply_volume_policy_to_bar(
        {
            "symbol": "XAUUSD",
            "timestamp": "2026-06-01T12:00:00+00:00",
            "open": 4400.0,
            "high": 4410.0,
            "low": 4390.0,
            "close": 4405.0,
            "volume": 5000.0,
            "source": "twelvedata",
        }
    )
    assert bar["volume"] == 0.0


def test_btc_volume_preserved() -> None:
    assert apply_volume_policy("BTCUSDT", 12.5) == 12.5
