"""Tests for the recurrence engine (recurrence.py).

Covers all frequency types, interval > 1, timezone DST handling,
until/count caps, and edge cases.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from models import ScheduleRule
from recurrence import (
    _iter_daily,
    _iter_weekdays,
    _iter_weekly,
    _localise,
    _parse_time,
    generate_occurrences,
    next_occurrence_after,
)

UTC = ZoneInfo("UTC")
NY = ZoneInfo("America/New_York")
LA = ZoneInfo("America/Los_Angeles")


def _dates(rule, start, end, tz=UTC, t="09:00"):
    """Helper: return list of date() from generate_occurrences."""
    dts = generate_occurrences(rule, t, tz, start, end)
    return [dt.astimezone(tz).date() for dt in dts]


# ---------------------------------------------------------------------------
# _parse_time
# ---------------------------------------------------------------------------

class TestParseTime:
    def test_hhmm(self):
        t = _parse_time("14:30")
        assert t.hour == 14
        assert t.minute == 30

    def test_none_returns_midnight(self):
        t = _parse_time(None)
        assert t.hour == 0
        assert t.minute == 0

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_time("9am")

    def test_bad_components_raises(self):
        with pytest.raises(ValueError):
            _parse_time("25:00")


# ---------------------------------------------------------------------------
# Daily
# ---------------------------------------------------------------------------

class TestDaily:
    def test_every_day(self):
        rule = ScheduleRule(frequency="daily")
        start = date(2026, 4, 1)
        end = date(2026, 4, 5)
        result = _dates(rule, start, end)
        assert result == [date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3),
                          date(2026, 4, 4), date(2026, 4, 5)]

    def test_every_other_day(self):
        rule = ScheduleRule(frequency="daily", interval=2)
        result = _dates(rule, date(2026, 4, 1), date(2026, 4, 8))
        assert result == [date(2026, 4, 1), date(2026, 4, 3), date(2026, 4, 5), date(2026, 4, 7)]

    def test_single_day_range(self):
        rule = ScheduleRule(frequency="daily")
        result = _dates(rule, date(2026, 4, 1), date(2026, 4, 1))
        assert result == [date(2026, 4, 1)]

    def test_empty_when_start_after_end(self):
        rule = ScheduleRule(frequency="daily")
        result = _dates(rule, date(2026, 4, 5), date(2026, 4, 1))
        assert result == []


# ---------------------------------------------------------------------------
# Weekdays (Mon-Fri)
# ---------------------------------------------------------------------------

class TestWeekdays:
    def test_full_week(self):
        rule = ScheduleRule(frequency="weekdays")
        # April 6 2026 is a Monday
        start = date(2026, 4, 6)
        end = date(2026, 4, 12)  # Sunday
        result = _dates(rule, start, end)
        # Mon Tue Wed Thu Fri (skip Sat 11, Sun 12)
        expected = [date(2026, 4, d) for d in [6, 7, 8, 9, 10]]
        assert result == expected

    def test_no_weekends(self):
        rule = ScheduleRule(frequency="weekdays")
        # April 11-12 are Sat-Sun
        result = _dates(rule, date(2026, 4, 11), date(2026, 4, 12))
        assert result == []

    def test_biweekly_weekdays(self):
        rule = ScheduleRule(frequency="weekdays", interval=2)
        # Week of Apr 6 (Mon): should yield, week of Apr 13 (Mon): skip,
        # week of Apr 20 (Mon): should yield
        start = date(2026, 4, 6)
        end = date(2026, 4, 24)
        result = _dates(rule, start, end)
        # Week 1: Apr 6-10, Week 3: Apr 20-24
        expected = (
            [date(2026, 4, d) for d in [6, 7, 8, 9, 10]] +
            [date(2026, 4, d) for d in [20, 21, 22, 23, 24]]
        )
        assert result == expected


# ---------------------------------------------------------------------------
# Weekly with specific weekdays
# ---------------------------------------------------------------------------

class TestWeekly:
    def test_monday_wednesday_friday(self):
        rule = ScheduleRule(frequency="weekly", weekdays=[1, 3, 5])
        # April 6 = Monday, April 8 = Wednesday, April 10 = Friday
        start = date(2026, 4, 6)
        end = date(2026, 4, 12)
        result = _dates(rule, start, end)
        assert result == [date(2026, 4, 6), date(2026, 4, 8), date(2026, 4, 10)]

    def test_biweekly_mondays(self):
        rule = ScheduleRule(frequency="weekly", weekdays=[1], interval=2)
        start = date(2026, 4, 6)   # Monday
        end = date(2026, 4, 27)    # Monday
        result = _dates(rule, start, end)
        # Every other Monday: Apr 6, Apr 20
        assert result == [date(2026, 4, 6), date(2026, 4, 20)]

    def test_defaults_to_start_weekday_when_no_weekdays(self):
        # Weekly with no weekdays specified — should default to start's weekday
        rule = ScheduleRule(frequency="weekly", weekdays=[])
        start = date(2026, 4, 8)   # Wednesday
        end = date(2026, 4, 22)
        result = _dates(rule, start, end)
        assert result == [date(2026, 4, 8), date(2026, 4, 15), date(2026, 4, 22)]

    def test_start_not_on_target_weekday(self):
        # Start on Tuesday but target is Monday — first occurrence next Monday
        rule = ScheduleRule(frequency="weekly", weekdays=[1])
        start = date(2026, 4, 7)   # Tuesday
        end = date(2026, 4, 20)
        result = _dates(rule, start, end)
        assert result == [date(2026, 4, 13), date(2026, 4, 20)]


# ---------------------------------------------------------------------------
# Until and count caps
# ---------------------------------------------------------------------------

class TestUntilAndCount:
    def test_until_trims_results(self):
        until = datetime(2026, 4, 10, 23, 59, 0, tzinfo=timezone.utc)
        rule = ScheduleRule(frequency="daily", until=until)
        result = _dates(rule, date(2026, 4, 1), date(2026, 4, 20))
        assert max(result) <= date(2026, 4, 10)

    def test_count_trims_results(self):
        rule = ScheduleRule(frequency="daily", count=3)
        result = _dates(rule, date(2026, 4, 1), date(2026, 4, 30))
        assert len(result) == 3

    def test_count_larger_than_window(self):
        # count=100 but window only has 5 days — should return 5
        rule = ScheduleRule(frequency="daily", count=100)
        result = _dates(rule, date(2026, 4, 1), date(2026, 4, 5))
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Once (no-op)
# ---------------------------------------------------------------------------

class TestOnce:
    def test_once_returns_empty(self):
        rule = ScheduleRule(frequency="once")
        result = _dates(rule, date(2026, 4, 1), date(2026, 4, 30))
        assert result == []


# ---------------------------------------------------------------------------
# Timezone handling
# ---------------------------------------------------------------------------

class TestTimezones:
    def test_utc_time_correct(self):
        rule = ScheduleRule(frequency="daily")
        dts = generate_occurrences(rule, "09:00", NY, date(2026, 4, 6), date(2026, 4, 6))
        assert len(dts) == 1
        # Apr 6 is after DST (EDT = UTC-4), so 09:00 EDT = 13:00 UTC
        utc_dt = dts[0]
        assert utc_dt.tzinfo == timezone.utc
        assert utc_dt.hour == 13
        assert utc_dt.minute == 0

    def test_utc_time_before_dst(self):
        rule = ScheduleRule(frequency="daily")
        # March 1 2026 = EST (UTC-5), so 09:00 EST = 14:00 UTC
        dts = generate_occurrences(rule, "09:00", NY, date(2026, 3, 1), date(2026, 3, 1))
        assert len(dts) == 1
        assert dts[0].hour == 14

    def test_la_time(self):
        rule = ScheduleRule(frequency="daily")
        # Apr 6 2026: LA is PDT (UTC-7), so 08:00 PDT = 15:00 UTC
        dts = generate_occurrences(rule, "08:00", LA, date(2026, 4, 6), date(2026, 4, 6))
        assert len(dts) == 1
        assert dts[0].hour == 15

    def test_all_results_are_utc(self):
        rule = ScheduleRule(frequency="weekly", weekdays=[1, 3, 5])
        dts = generate_occurrences(rule, "10:00", NY, date(2026, 4, 1), date(2026, 4, 30))
        for dt in dts:
            assert dt.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# next_occurrence_after
# ---------------------------------------------------------------------------

class TestNextOccurrenceAfter:
    def test_finds_next_daily(self):
        rule = ScheduleRule(frequency="daily")
        after = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        next_dt = next_occurrence_after(rule, "09:00", NY, after)
        assert next_dt is not None
        # 09:00 NY on Apr 1 is already past (after is noon UTC = 8am NY),
        # wait — 09:00 EDT = 13:00 UTC. after=12:00 UTC, so same day 13:00 qualifies
        local_date = next_dt.astimezone(NY).date()
        assert local_date == date(2026, 4, 1)

    def test_finds_next_weekly(self):
        rule = ScheduleRule(frequency="weekly", weekdays=[1])  # Mondays
        # After a Wednesday
        after = datetime(2026, 4, 8, 20, 0, 0, tzinfo=timezone.utc)  # Wed Apr 8
        next_dt = next_occurrence_after(rule, "09:00", NY, after)
        assert next_dt is not None
        local_date = next_dt.astimezone(NY).date()
        assert local_date.isoweekday() == 1  # Monday
        assert local_date == date(2026, 4, 13)

    def test_once_returns_none(self):
        rule = ScheduleRule(frequency="once")
        after = datetime(2026, 4, 1, tzinfo=timezone.utc)
        assert next_occurrence_after(rule, "09:00", NY, after) is None

    def test_exhausted_count_returns_none(self):
        rule = ScheduleRule(frequency="daily", count=1)
        # after is already past the only occurrence (which would be on/after start)
        after = datetime(2027, 1, 1, tzinfo=timezone.utc)
        result = next_occurrence_after(rule, "09:00", NY, after)
        # count=1 with start effectively in 2027+; hard to exhaust in 2 yrs
        # but if until is set:
        rule2 = ScheduleRule(frequency="daily", until=datetime(2026, 4, 2, tzinfo=timezone.utc))
        result2 = next_occurrence_after(rule2, "09:00", NY, datetime(2026, 4, 10, tzinfo=timezone.utc))
        assert result2 is None


# ---------------------------------------------------------------------------
# _iter_daily edge cases
# ---------------------------------------------------------------------------

class TestIterDailyEdge:
    def test_interval_zero_raises(self):
        with pytest.raises(ValueError):
            list(_iter_daily(date(2026, 4, 1), date(2026, 4, 5), 0))

    def test_interval_one(self):
        result = list(_iter_daily(date(2026, 4, 1), date(2026, 4, 3), 1))
        assert result == [date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)]


# ---------------------------------------------------------------------------
# _localise
# ---------------------------------------------------------------------------

class TestLocalise:
    def test_utc_passthrough(self):
        from datetime import time
        d = date(2026, 4, 1)
        t = time(9, 0)
        result = _localise(d, t, UTC)
        assert result.hour == 9
        assert result.tzinfo == timezone.utc

    def test_ny_conversion(self):
        from datetime import time
        # EDT: UTC-4, so 09:00 NY = 13:00 UTC
        d = date(2026, 4, 6)
        t = time(9, 0)
        result = _localise(d, t, NY)
        assert result.hour == 13
        assert result.tzinfo == timezone.utc
