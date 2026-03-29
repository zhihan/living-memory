"""ICS (iCalendar) export for occurrences and series.

Uses the ``icalendar`` library to build RFC 5545 VCALENDAR objects.

Public API:
  occurrence_to_ics(occurrence, series) -> Calendar
  series_to_ics(series, occurrences)    -> Calendar
  calendar_to_bytes(cal)                -> bytes
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Sequence

try:
    from icalendar import Calendar, Event, vText, vDatetime
except ImportError as exc:
    raise ImportError(
        "The 'icalendar' library is required for ICS export. "
        "Install it with: pip install icalendar"
    ) from exc

from models import Occurrence, Series

_PROD_ID = "-//Event Ledger//Event Ledger 1.0//EN"


def _parse_utc(iso_str: str) -> datetime:
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_event(occurrence: Occurrence, series: Series) -> Event:
    ev = Event()
    title = (occurrence.overrides and occurrence.overrides.title) or series.title
    ev.add("summary", title)
    ev.add("uid", f"{occurrence.occurrence_id}@event-ledger.app")
    dtstart = _parse_utc(occurrence.scheduled_for)
    duration_minutes = (
        (occurrence.overrides and occurrence.overrides.duration_minutes)
        or series.default_duration_minutes
        or 60
    )
    dtend = dtstart + timedelta(minutes=duration_minutes)
    ev.add("dtstart", dtstart)
    ev.add("dtend", dtend)
    ev.add("dtstamp", datetime.now(timezone.utc))
    location = (
        (occurrence.overrides and occurrence.overrides.location)
        or series.default_location
    )
    if location:
        ev.add("location", location)
    notes = occurrence.overrides and occurrence.overrides.notes
    online_link = (
        (occurrence.overrides and occurrence.overrides.online_link)
        or series.default_online_link
    )
    desc_parts: list[str] = []
    if online_link:
        desc_parts.append(f"Online link: {online_link}")
    if notes:
        desc_parts.append(notes)
    elif series.description:
        desc_parts.append(series.description)
    if desc_parts:
        ev.add("description", "\n".join(desc_parts))
    status_map = {
        "scheduled": "CONFIRMED",
        "rescheduled": "CONFIRMED",
        "completed": "COMPLETED",
        "cancelled": "CANCELLED",
    }
    ev.add("status", status_map.get(occurrence.status, "CONFIRMED"))
    base_url = os.environ.get("APP_BASE_URL", "https://app.event-ledger.app")
    ev.add("url", f"{base_url}/occurrences/{occurrence.occurrence_id}")
    return ev


def occurrence_to_ics(occurrence: Occurrence, series: Series) -> Calendar:
    """Build a VCALENDAR with a single VEVENT for occurrence."""
    cal = Calendar()
    cal.add("prodid", _PROD_ID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", series.title)
    cal.add("x-wr-timezone", "UTC")
    cal.add_component(_build_event(occurrence, series))
    return cal


def series_to_ics(
    series: Series,
    occurrences: Sequence[Occurrence],
    *,
    include_cancelled: bool = False,
) -> Calendar:
    """Build a VCALENDAR with one VEVENT per occurrence."""
    cal = Calendar()
    cal.add("prodid", _PROD_ID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", series.title)
    cal.add("x-wr-timezone", "UTC")
    for occ in occurrences:
        if occ.status == "cancelled" and not include_cancelled:
            continue
        cal.add_component(_build_event(occ, series))
    return cal


def calendar_to_bytes(cal: Calendar) -> bytes:
    """Serialize a Calendar object to raw ICS bytes."""
    return cal.to_ical()
