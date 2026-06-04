"""Format economic calendar for news agent prompts."""

from datetime import datetime, timezone

from app.config import settings
from app.schemas.agent import EconomicEventSchema, MarketSnapshot
from app.services.finnhub_calendar import find_imminent_event, minutes_until_event


def format_economic_calendar_block(snapshot: MarketSnapshot) -> str:
    events = snapshot.upcoming_events
    if not events:
        return "\nالتقويم الاقتصادي (Finnhub، high فقط — 24 ساعة): لا أحداث عالية التأثير قادمة."

    ref = snapshot.timestamp
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    lines = ["\nالتقويم الاقتصادي (Finnhub — high impact، 24 ساعة):"]
    for idx, ev in enumerate(events[:12], start=1):
        mins = minutes_until_event(ev.event_time, ref)
        when = ev.event_time.strftime("%Y-%m-%d %H:%M UTC")
        timing = f"بعد {mins:.0f} دقيقة" if mins >= 0 else f"منذ {abs(mins):.0f} دقيقة"
        est = f" | تقدير {ev.estimate}" if ev.estimate is not None else ""
        lines.append(f"{idx}. [{ev.country}] {ev.event} — {when} ({timing}){est}")

    imminent = find_imminent_event(events, ref, within_minutes=settings.economic_calendar_news_warn_minutes)
    if imminent:
        mins = minutes_until_event(imminent.event_time, ref)
        lines.append(
            f"\n⚠️ تحذير: حدث عالي التأثير خلال {mins:.0f} دقيقة — "
            f"{imminent.event} ({imminent.country}). يُفضل الحذر أو NEUTRAL."
        )

    lines.append(
        f"\nقواعد: إن كان حدث خلال {settings.economic_calendar_news_warn_minutes} دقيقة "
        "اذكر التحذير في reasoning. حول الأحداث الكبرى قدّم NEUTRAL بثقة أعلى."
    )
    return "\n".join(lines)
