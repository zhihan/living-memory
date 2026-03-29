"""Tests for occurrence_service.py."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import Occurrence, OccurrenceOverrides, ScheduleRule, Series
from occurrence_service import (
    complete_occurrence,
    edit_occurrence,
    generate_and_save,
    reschedule_occurrence,
    skip_occurrence,
)


def _make_series(**kwargs) -> Series:
    defaults = dict(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Standup",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),  # Mondays
        default_time="09:00",
    )
    defaults.update(kwargs)
    return Series(**defaults)


class TestGenerateAndSave:
    def test_creates_occurrences_for_mondays(self):
        series = _make_series()
        # April 6, 13, 20, 27 2026 are Mondays
        created: list[Occurrence] = []

        with patch("occurrence_service.list_occurrences_for_series", return_value=[]),              patch("occurrence_service.save_occurrences_batch", side_effect=lambda lst: created.extend(lst)):
            result = generate_and_save(series, "UTC", date(2026, 4, 1), date(2026, 4, 30))

        assert len(result) == 4
        dates = [
            datetime.fromisoformat(o.scheduled_for).date()
            for o in result
        ]
        from datetime import date as d
        assert d(2026, 4, 6) in dates
        assert d(2026, 4, 13) in dates
        assert d(2026, 4, 20) in dates
        assert d(2026, 4, 27) in dates

    def test_skips_existing_occurrences(self):
        series = _make_series()
        # Apr 6 already exists
        existing = [Occurrence(
            occurrence_id="occ-existing",
            series_id="s-1",
            workspace_id="ws-1",
            scheduled_for="2026-04-06T09:00:00+00:00",
        )]

        with patch("occurrence_service.list_occurrences_for_series", return_value=existing),              patch("occurrence_service.save_occurrences_batch") as mock_save:
            result = generate_and_save(series, "UTC", date(2026, 4, 1), date(2026, 4, 13))

        # Should only create Apr 13; Apr 6 already exists
        assert len(result) == 1
        saved_batch = mock_save.call_args[0][0]
        assert len(saved_batch) == 1

    def test_returns_empty_for_no_window_matches(self):
        # "once" rule generates nothing
        series = _make_series(schedule_rule=ScheduleRule(frequency="once"))

        with patch("occurrence_service.list_occurrences_for_series", return_value=[]),              patch("occurrence_service.save_occurrences_batch") as mock_save:
            result = generate_and_save(series, "UTC", date(2026, 4, 1), date(2026, 4, 30))

        assert result == []
        mock_save.assert_not_called()

    def test_assigns_workspace_id(self):
        series = _make_series(workspace_id="ws-99")
        with patch("occurrence_service.list_occurrences_for_series", return_value=[]),              patch("occurrence_service.save_occurrences_batch") as mock_save:
            result = generate_and_save(series, "UTC", date(2026, 4, 6), date(2026, 4, 6))

        assert all(o.workspace_id == "ws-99" for o in result)

    def test_occurrence_ids_are_unique(self):
        series = _make_series()
        with patch("occurrence_service.list_occurrences_for_series", return_value=[]),              patch("occurrence_service.save_occurrences_batch"):
            result = generate_and_save(series, "UTC", date(2026, 4, 1), date(2026, 4, 30))

        ids = [o.occurrence_id for o in result]
        assert len(ids) == len(set(ids))


class TestSkipComplete:
    def _mock_occ(self, status="scheduled"):
        return Occurrence(
            occurrence_id="occ-1", series_id="s-1", workspace_id="ws-1",
            scheduled_for="2026-04-06T13:00:00+00:00", status=status,
        )

    def test_skip_sets_cancelled(self):
        updated = self._mock_occ(status="cancelled")
        with patch("occurrence_service.update_occurrence", return_value=updated) as mock_upd:
            result = skip_occurrence("occ-1")
        mock_upd.assert_called_once_with("occ-1", {"status": "cancelled"})
        assert result.status == "cancelled"

    def test_complete_sets_completed(self):
        updated = self._mock_occ(status="completed")
        with patch("occurrence_service.update_occurrence", return_value=updated) as mock_upd:
            result = complete_occurrence("occ-1")
        mock_upd.assert_called_once_with("occ-1", {"status": "completed"})

    def test_reschedule(self):
        updated = self._mock_occ(status="rescheduled")
        with patch("occurrence_service.update_occurrence", return_value=updated) as mock_upd:
            result = reschedule_occurrence("occ-1", "2026-04-08T13:00:00+00:00")
        call_args = mock_upd.call_args[0]
        assert call_args[1]["status"] == "rescheduled"
        assert call_args[1]["scheduled_for"] == "2026-04-08T13:00:00+00:00"

    def test_edit_occurrence(self):
        overrides = OccurrenceOverrides(location="Room B", time="10:00")
        updated = self._mock_occ()
        with patch("occurrence_service.update_occurrence", return_value=updated) as mock_upd:
            edit_occurrence("occ-1", overrides)
        call_args = mock_upd.call_args[0]
        assert call_args[0] == "occ-1"
        saved = call_args[1]["overrides"]
        assert saved["location"] == "Room B"
        assert saved["time"] == "10:00"
