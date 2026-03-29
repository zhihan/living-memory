"""Recurrence engine: deterministic occurrence generation from ScheduleRule.

Given a Series with a ScheduleRule, this module generates the list of
UTC datetimes at which occurrences should be scheduled, within a
caller-specified window.

Design goals:
- Pure function — no Firestore access, no side effects.
- Timezone-aware throughout (workspace timezone drives wall-clock logic).
- Idempotent: calling generate_occurrences() with the same inputs always
  returns the same list, so callers can safely regenerate and diff.
- Respects until / count caps from the rule.
- Single-occurrence overrides (skip, reschedule) are handled at the
  storage layer, not here — this engine only produces the base schedule.

Usage:
    from recurrence import generate_occurrences
    from models import ScheduleRule
    from datetime import date
    from zoneinfo import ZoneInfo

    rule = ScheduleRule(frequency="weekly", weekdays=[1, 3])  # Mon/Wed
    occurrences = generate_occurrences(
        rule=rule,
        default_time="09:00",
        timezone=ZoneInfo("America/New_York"),
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )
    # -> list of UTC datetime objects
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterator
from zoneinfo import ZoneInfo

from models import ScheduleRule

# Maximum number of occurrences we will ever generate in one call, as a
# safety guard against infinite loops from misconfigured rules.
_MAX_OCCURRENCES = 5000


def generate_occurrences(
    rule: ScheduleRule,
    default_time: str | None,
    timezone: ZoneInfo,
    start_date: date,
    end_date: date,
) -> list[datetime]:
    """Generate UTC datetimes for occurrences within [start_date, end_date].

    Args:
        rule:         The ScheduleRule driving the recurrence.
        default_time: Wall-clock time of day as "HH:MM" in *timezone*.
                      If None, midnight (00:00) is used.
        timezone:     The workspace timezone used to interpret wall-clock times.
        start_date:   First day (inclusive) to consider, in *timezone*.
        end_date:     Last day (inclusive) to consider, in *timezone*.

    Returns:
        Sorted list of UTC datetime objects. Empty list if no occurrences fall
        in the window or the rule is ``frequency="once"`` with no start_date
        anchor.
    """
    wall_time = _parse_time(default_time)
    results: list[datetime] = []

    for candidate_date in _iter_dates(rule, start_date, end_date):
        utc_dt = _localise(candidate_date, wall_time, timezone)
        results.append(utc_dt)
        if len(results) >= _MAX_OCCURRENCES:
            break

    # Apply count cap from the rule (after windowing)
    if rule.count is not None and len(results) > rule.count:
        results = results[: rule.count]

    return results


def next_occurrence_after(
    rule: ScheduleRule,
    default_time: str | None,
    timezone: ZoneInfo,
    after: datetime,
) -> datetime | None:
    """Return the first occurrence strictly after *after* (UTC).

    Searches up to 2 years ahead. Returns None if no occurrence found
    (e.g. rule has already exhausted its count or passed its until date).
    """
    after_date = after.astimezone(timezone).date()
    search_end = after_date + timedelta(days=730)
    wall_time = _parse_time(default_time)

    count_seen = 0
    for candidate_date in _iter_dates(rule, after_date, search_end):
        utc_dt = _localise(candidate_date, wall_time, timezone)
        count_seen += 1
        if rule.count is not None and count_seen > rule.count:
            return None
        if utc_dt > after:
            return utc_dt

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iter_dates(
    rule: ScheduleRule, start_date: date, end_date: date
) -> Iterator[date]:
    """Yield candidate dates matching *rule* within [start_date, end_date].

    Respects rule.until but not rule.count (callers handle that).
    """
    if rule.frequency == "once":
        # A "once" rule with no anchor produces nothing; the occurrence date
        # must be specified externally (e.g. via series.default_time and an
        # explicit scheduled_for at creation time).
        return

    until_date: date | None = None
    if rule.until is not None:
        until_dt = rule.until
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
        until_date = until_dt.date()

    effective_end = end_date
    if until_date is not None and until_date < effective_end:
        effective_end = until_date

    if rule.frequency == "daily":
        yield from _iter_daily(start_date, effective_end, rule.interval)
    elif rule.frequency == "weekdays":
        yield from _iter_weekdays(start_date, effective_end, rule.interval)
    elif rule.frequency in ("weekly", "custom"):
        yield from _iter_weekly(start_date, effective_end, rule.weekdays, rule.interval)
    else:
        raise ValueError(f"Unknown frequency: {rule.frequency!r}")


def _iter_daily(start: date, end: date, interval: int) -> Iterator[date]:
    """Yield every *interval* days from *start* to *end* inclusive."""
    if interval < 1:
        raise ValueError(f"interval must be >= 1, got {interval}")
    current = start
    while current <= end:
        yield current
        current += timedelta(days=interval)


def _iter_weekdays(start: date, end: date, interval: int) -> Iterator[date]:
    """Yield Monday-Friday dates from *start* to *end*, stepping by *interval* weeks.

    When interval > 1, we advance by *interval* weeks after each full M-F run.
    When interval == 1, every weekday is yielded.
    """
    if interval < 1:
        raise ValueError(f"interval must be >= 1, got {interval}")
    if interval == 1:
        current = start
        while current <= end:
            if current.isoweekday() <= 5:  # Mon=1 … Fri=5
                yield current
            current += timedelta(days=1)
    else:
        # Advance week by week, emitting Mon-Fri each retained week
        # Find the Monday of the start week
        week_start = start - timedelta(days=start.isoweekday() - 1)
        while week_start <= end:
            for day_offset in range(5):  # Mon=0 … Fri=4
                candidate = week_start + timedelta(days=day_offset)
                if start <= candidate <= end:
                    yield candidate
            week_start += timedelta(weeks=interval)


def _iter_weekly(
    start: date, end: date, weekdays: list[int], interval: int
) -> Iterator[date]:
    """Yield dates matching *weekdays* (ISO 1=Mon…7=Sun) with *interval* week cadence.

    When weekdays is empty, defaults to the same weekday as *start*.
    """
    if interval < 1:
        raise ValueError(f"interval must be >= 1, got {interval}")

    effective_weekdays = weekdays if weekdays else [start.isoweekday()]
    effective_weekdays_set = set(effective_weekdays)

    # Anchor to the Monday of the start week
    week_start = start - timedelta(days=start.isoweekday() - 1)

    while week_start <= end:
        for iso_wd in sorted(effective_weekdays_set):
            candidate = week_start + timedelta(days=iso_wd - 1)
            if start <= candidate <= end:
                yield candidate
        week_start += timedelta(weeks=interval)


def _parse_time(time_str: str | None) -> time:
    """Parse "HH:MM" -> datetime.time. Returns midnight if None."""
    if time_str is None:
        return time(0, 0)
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str!r}. Expected HH:MM")
    try:
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid time format: {time_str!r}") from exc


def _localise(d: date, t: time, tz: ZoneInfo) -> datetime:
    """Combine *d* and *t* in *tz*, then convert to UTC.

    Handles DST folds using fold=0 (first/standard occurrence).
    """
    local_dt = datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)
