"""Market session schedule — Iraq timezone (Asia/Baghdad)."""



from __future__ import annotations



from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo



from app.config.assets import ASSETS



BAGHDAD = ZoneInfo("Asia/Baghdad")



SCHEDULE_LABELS: dict[str, str] = {

    "BTCUSDT": "مفتوح 24/7 بدون توقف",

    "XAUUSD": "مفتوح الاثنين–الجمعة | مغلق الجمعة 11م – الاثنين 1ص (توقيت العراق)",

    "EURUSD": "مفتوح 24/5 | الاثنين–الجمعة (توقيت العراق) | مغلق السبت والأحد",

    "USDJPY": "مفتوح 24/5 | الاثنين–الجمعة (توقيت العراق) | مغلق السبت والأحد",

    "GBPUSD": "مفتوح 24/5 | الاثنين–الجمعة (توقيت العراق) | مغلق السبت والأحد",

}





def is_market_open(symbol: str, at: datetime | None = None) -> bool:

    """Return True if trading/signals are allowed for the symbol."""

    asset = ASSETS.get(symbol)

    if asset is None:

        return False

    schedule = asset.market_schedule

    if schedule == "24_7":

        return True

    if schedule == "xauusd":

        return _is_xauusd_open(at)

    if schedule == "forex_24_5":

        return _is_forex_24_5_open(at)

    return False





def _is_xauusd_open(at: datetime | None = None) -> bool:

    local = (at or datetime.now(timezone.utc)).astimezone(BAGHDAD)

    weekday = local.weekday()  # Mon=0 .. Sun=6



    if weekday in (5, 6):  # Saturday, Sunday

        return False

    if weekday == 4 and local.hour >= 23:  # Friday from 11 PM

        return False

    if weekday == 0 and local.hour < 1:  # Monday before 1 AM

        return False

    return True





def _is_forex_24_5_open(at: datetime | None = None) -> bool:

    """Forex 24/5 — open Mon 00:00 through Fri 23:59 Iraq time."""

    local = (at or datetime.now(timezone.utc)).astimezone(BAGHDAD)

    return local.weekday() < 5  # Mon=0 .. Fri=4





def next_market_open(symbol: str, at: datetime | None = None) -> datetime | None:

    if is_market_open(symbol, at):

        return None



    asset = ASSETS.get(symbol)

    if asset is None:

        return None



    local = (at or datetime.now(timezone.utc)).astimezone(BAGHDAD)



    if asset.market_schedule == "xauusd":

        weekday = local.weekday()

        if weekday == 0 and local.hour < 1:

            open_local = local.replace(hour=1, minute=0, second=0, microsecond=0)

        elif weekday == 4 and local.hour >= 23:

            open_local = (local + timedelta(days=3)).replace(

                hour=1, minute=0, second=0, microsecond=0

            )

        elif weekday == 5:

            open_local = (local + timedelta(days=2)).replace(

                hour=1, minute=0, second=0, microsecond=0

            )

        elif weekday == 6:

            open_local = (local + timedelta(days=1)).replace(

                hour=1, minute=0, second=0, microsecond=0

            )

        else:

            open_local = local.replace(hour=1, minute=0, second=0, microsecond=0)

            if open_local <= local:

                open_local += timedelta(days=1)

        return open_local.astimezone(timezone.utc)



    if asset.market_schedule == "forex_24_5":

        weekday = local.weekday()

        if weekday == 5:  # Saturday → Monday 00:00

            open_local = (local + timedelta(days=2)).replace(

                hour=0, minute=0, second=0, microsecond=0

            )

        elif weekday == 6:  # Sunday → Monday 00:00

            open_local = (local + timedelta(days=1)).replace(

                hour=0, minute=0, second=0, microsecond=0

            )

        else:

            return None

        return open_local.astimezone(timezone.utc)



    return None


def next_market_close(symbol: str, at: datetime | None = None) -> datetime | None:
    """Next scheduled close time in UTC, or None when market is already closed or 24/7."""
    if not is_market_open(symbol, at):
        return None

    asset = ASSETS.get(symbol)
    if asset is None:
        return None

    local = (at or datetime.now(timezone.utc)).astimezone(BAGHDAD)

    if asset.market_schedule == "xauusd":
        weekday = local.weekday()
        if weekday > 4 or (weekday == 4 and local.hour >= 23):
            return None
        days_until_friday = 4 - weekday
        close_local = (local + timedelta(days=days_until_friday)).replace(
            hour=23, minute=0, second=0, microsecond=0
        )
        if close_local <= local:
            return None
        return close_local.astimezone(timezone.utc)

    if asset.market_schedule == "forex_24_5":
        weekday = local.weekday()
        if weekday > 4:
            return None
        days_until_friday = 4 - weekday
        close_local = (local + timedelta(days=days_until_friday)).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
        if close_local <= local:
            return None
        return close_local.astimezone(timezone.utc)

    return None


def next_h1_bar_close(at: datetime | None = None) -> datetime:

    """Next hourly candle close (UTC)."""

    now = at or datetime.now(timezone.utc)

    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)





def is_gold_trading_session(at: datetime | None = None) -> bool:

    """London 10:00–19:00 or New York 16:00–01:00 Iraq time (XAUUSD only)."""

    if not _is_xauusd_open(at):

        return False



    local = (at or datetime.now(timezone.utc)).astimezone(BAGHDAD)

    hour = local.hour



    london = 10 <= hour < 19

    new_york = hour >= 16 or hour < 1

    return london or new_york





def next_signal_opportunity(

    symbol: str,

    last_signal_at: datetime | None,

    cooldown_hours: float,

    at: datetime | None = None,

) -> datetime | None:

    """Earliest next signal evaluation time (UTC). None if market closed."""

    if not is_market_open(symbol, at):

        return None



    now = at or datetime.now(timezone.utc)

    next_bar = next_h1_bar_close(now)



    if last_signal_at is None:

        return next_bar



    if last_signal_at.tzinfo is None:

        last_signal_at = last_signal_at.replace(tzinfo=timezone.utc)



    cooldown_end = last_signal_at + timedelta(hours=cooldown_hours)

    return max(next_bar, cooldown_end)





def symbols_with_scheduled_reopen() -> list[str]:

    """Assets that close on weekends and need bootstrap on reopen."""

    return [

        sym

        for sym, cfg in ASSETS.items()

        if cfg.market_schedule in ("xauusd", "forex_24_5")

    ]


