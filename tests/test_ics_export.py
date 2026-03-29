"""Tests for ICS generation (ics_export.py)."""
from __future__ import annotations
import sys, types, uuid
from datetime import datetime, timezone
import pytest

for mod_name in ['firebase_admin', 'firebase_admin.auth', 'google', 'google.cloud', 'google.cloud.firestore']:
    if mod_name not in sys.modules:
        m = types.ModuleType(mod_name)
        if mod_name == 'firebase_admin':
            m._apps = {}
        sys.modules[mod_name] = m

from models import Occurrence, OccurrenceOverrides, Series, ScheduleRule


def _series(**kwargs):
    defaults = dict(series_id='s1', workspace_id='ws1', kind='meeting', title='Team Sync', schedule_rule=ScheduleRule(frequency='weekly', weekdays=[1]), default_time='14:00', default_duration_minutes=45, default_location='Room 101', default_online_link='https://zoom.us/j/123', description='Weekly team meeting')
    defaults.update(kwargs)
    return Series(**defaults)


def _occ(**kwargs):
    defaults = dict(occurrence_id=str(uuid.uuid4()), series_id='s1', workspace_id='ws1', scheduled_for='2026-04-07T14:00:00+00:00', status='scheduled')
    defaults.update(kwargs)
    return Occurrence(**defaults)


class TestOccurrenceToIcs:
    def test_basic_event(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        cal = occurrence_to_ics(_occ(), _series())
        raw = calendar_to_bytes(cal)
        assert b'BEGIN:VCALENDAR' in raw
        assert b'BEGIN:VEVENT' in raw
        assert b'END:VEVENT' in raw
        assert b'Team Sync' in raw

    def test_uid_stable(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        raw = calendar_to_bytes(occurrence_to_ics(_occ(occurrence_id='fixed-occ-id'), _series()))
        assert b'fixed-occ-id@event-ledger.app' in raw

    def test_location_included(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        raw = calendar_to_bytes(occurrence_to_ics(_occ(), _series()))
        assert b'Room 101' in raw

    def test_override_title(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        occ = _occ(overrides=OccurrenceOverrides(title='Special Sync', location='Room 202'))
        raw = calendar_to_bytes(occurrence_to_ics(occ, _series()))
        assert b'Special Sync' in raw
        assert b'Room 202' in raw

    def test_dtstart_correct(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        raw = calendar_to_bytes(occurrence_to_ics(_occ(scheduled_for='2026-04-07T14:00:00+00:00'), _series()))
        assert b'20260407T140000Z' in raw

    def test_dtend_uses_duration(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        raw = calendar_to_bytes(occurrence_to_ics(_occ(scheduled_for='2026-04-07T14:00:00+00:00'), _series(default_duration_minutes=90)))
        assert b'20260407T153000Z' in raw

    def test_cancelled_status(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        raw = calendar_to_bytes(occurrence_to_ics(_occ(status='cancelled'), _series()))
        assert b'STATUS:CANCELLED' in raw

    def test_online_link_in_description(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        raw = calendar_to_bytes(occurrence_to_ics(_occ(), _series()))
        assert b'zoom.us' in raw

    def test_default_duration_fallback(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        raw = calendar_to_bytes(occurrence_to_ics(_occ(scheduled_for='2026-04-07T14:00:00+00:00'), _series(default_duration_minutes=None)))
        assert b'20260407T150000Z' in raw


class TestSeriesToIcs:
    def test_multiple_events(self):
        from ics_export import series_to_ics, calendar_to_bytes
        occs = [_occ(scheduled_for=f'2026-04-{7+7*i:02d}T14:00:00+00:00') for i in range(3)]
        raw = calendar_to_bytes(series_to_ics(_series(), occs))
        assert raw.count(b'BEGIN:VEVENT') == 3

    def test_cancelled_excluded_by_default(self):
        from ics_export import series_to_ics, calendar_to_bytes
        occs = [_occ(scheduled_for='2026-04-07T14:00:00+00:00', status='scheduled'), _occ(scheduled_for='2026-04-14T14:00:00+00:00', status='cancelled')]
        raw = calendar_to_bytes(series_to_ics(_series(), occs))
        assert raw.count(b'BEGIN:VEVENT') == 1

    def test_cancelled_included_when_flag_set(self):
        from ics_export import series_to_ics, calendar_to_bytes
        occs = [_occ(scheduled_for='2026-04-07T14:00:00+00:00', status='scheduled'), _occ(scheduled_for='2026-04-14T14:00:00+00:00', status='cancelled')]
        raw = calendar_to_bytes(series_to_ics(_series(), occs, include_cancelled=True))
        assert raw.count(b'BEGIN:VEVENT') == 2

    def test_empty_series(self):
        from ics_export import series_to_ics, calendar_to_bytes
        raw = calendar_to_bytes(series_to_ics(_series(), []))
        assert b'BEGIN:VCALENDAR' in raw
        assert b'BEGIN:VEVENT' not in raw


class TestCalendarToBytes:
    def test_returns_bytes(self):
        from ics_export import occurrence_to_ics, calendar_to_bytes
        result = calendar_to_bytes(occurrence_to_ics(_occ(), _series()))
        assert isinstance(result, bytes)
        assert len(result) > 0
