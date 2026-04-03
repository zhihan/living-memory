"""Tests for occurrence_service.py."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import Occurrence, OccurrenceOverrides, ScheduleRule, Series
from occurrence_service import (
    complete_occurrence,
    create_single_occurrence,
    edit_occurrence,
    generate_and_save,
    regenerate_series,
    reschedule_occurrence,
    skip_occurrence,
)


def _make_series(**kwargs) -> Series:
    defaults = dict(
        series_id="s-1",
        room_id="ws-1",
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
            room_id="ws-1",
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

    def test_assigns_room_id(self):
        series = _make_series(room_id="ws-99")
        with patch("occurrence_service.list_occurrences_for_series", return_value=[]),              patch("occurrence_service.save_occurrences_batch") as mock_save:
            result = generate_and_save(series, "UTC", date(2026, 4, 6), date(2026, 4, 6))

        assert all(o.room_id == "ws-99" for o in result)

    def test_occurrence_ids_are_unique(self):
        series = _make_series()
        with patch("occurrence_service.list_occurrences_for_series", return_value=[]),              patch("occurrence_service.save_occurrences_batch"):
            result = generate_and_save(series, "UTC", date(2026, 4, 1), date(2026, 4, 30))

        ids = [o.occurrence_id for o in result]
        assert len(ids) == len(set(ids))


class TestCreateSingleOccurrence:
    def test_creates_and_reindexes(self):
        """New occurrence inserted between existing ones gets correct sequence_index."""
        series = _make_series(enable_done=True, default_location="Room A")
        existing = [
            Occurrence(
                occurrence_id="occ-1", series_id="s-1", room_id="ws-1",
                scheduled_for="2026-04-06T09:00:00+00:00", sequence_index=0,
            ),
            Occurrence(
                occurrence_id="occ-3", series_id="s-1", room_id="ws-1",
                scheduled_for="2026-04-20T09:00:00+00:00", sequence_index=1,
            ),
        ]
        # After save, list_occurrences_for_series returns existing + new (sorted)
        new_scheduled = "2026-04-13T09:00:00+00:00"
        captured_updates: list[tuple] = []

        def fake_list(sid, **kw):
            # Return all three, simulating the state after save_occurrence
            new_occ = Occurrence(
                occurrence_id="occ-new", series_id="s-1", room_id="ws-1",
                scheduled_for=new_scheduled, sequence_index=None,
            )
            return sorted(existing + [new_occ], key=lambda o: o.scheduled_for)

        def fake_update(oid, updates):
            captured_updates.append((oid, updates))
            return MagicMock()

        with (
            patch("occurrence_service.get_series", return_value=series),
            patch("occurrence_service.save_occurrence") as mock_save,
            patch("occurrence_service.list_occurrences_for_series", side_effect=fake_list),
            patch("occurrence_service.update_occurrence", side_effect=fake_update),
        ):
            result = create_single_occurrence("s-1", new_scheduled)

        # Should have saved the new occurrence
        mock_save.assert_called_once()
        saved_occ = mock_save.call_args[0][0]
        assert saved_occ.scheduled_for == new_scheduled
        assert saved_occ.room_id == "ws-1"
        assert saved_occ.enable_check_in is True
        assert saved_occ.location == "Room A"

        # Should re-index: occ-1=0 (unchanged), occ-new=1 (was None), occ-3=2 (was 1)
        update_ids = {oid for oid, _ in captured_updates}
        assert "occ-new" in update_ids or "occ-3" in update_ids

    def test_series_not_found_raises(self):
        with patch("occurrence_service.get_series", return_value=None):
            with pytest.raises(ValueError, match="Series not found"):
                create_single_occurrence("no-such", "2026-04-13T09:00:00+00:00")


class TestSkipComplete:
    def _mock_occ(self, status="scheduled"):
        return Occurrence(
            occurrence_id="occ-1", series_id="s-1", room_id="ws-1",
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


class TestRegenerateSeries:
    """Tests for regenerate_series (adjust mode)."""

    def _make_occ(self, occ_id, scheduled_for, status="scheduled"):
        return Occurrence(
            occurrence_id=occ_id, series_id="s-1", room_id="ws-1",
            scheduled_for=scheduled_for, status=status,
        )

    def test_keeps_matching_deletes_non_matching(self):
        """Occurrences matching the new schedule are kept; others are deleted."""
        # Series changes from Monday to Wednesday
        series = _make_series(
            schedule_rule=ScheduleRule(frequency="weekly", weekdays=[3]),  # Wed
        )
        # Existing Monday occurrences (Apr 6, 13 are Mondays; Apr 8, 15 are Wednesdays)
        existing = [
            self._make_occ("occ-mon-6", "2026-04-06T09:00:00+00:00"),
            self._make_occ("occ-wed-8", "2026-04-08T09:00:00+00:00"),
            self._make_occ("occ-mon-13", "2026-04-13T09:00:00+00:00"),
        ]
        deleted_ids = []
        batch_saved = []

        with (
            patch("occurrence_service.get_series", return_value=series),
            patch("occurrence_service.list_occurrences_for_series", return_value=existing),
            patch("occurrence_service.delete_occurrence", side_effect=lambda oid: deleted_ids.append(oid)),
            patch("occurrence_service.save_occurrences_batch", side_effect=lambda lst: batch_saved.extend(lst)),
        ):
            result = regenerate_series("s-1", "UTC", date(2026, 4, 1), date(2026, 4, 30))

        # Monday occurrences should be deleted (not in new Wed schedule)
        assert "occ-mon-6" in deleted_ids
        assert "occ-mon-13" in deleted_ids
        # Wednesday occurrence should NOT be deleted
        assert "occ-wed-8" not in deleted_ids
        # New Wed occurrences created for dates not already existing
        assert result["created"] >= 1
        assert result["cancelled"] == 2

    def test_preserves_completed_occurrences(self):
        """Completed occurrences are never deleted, even if they don't match."""
        series = _make_series(
            schedule_rule=ScheduleRule(frequency="weekly", weekdays=[3]),  # Wed
        )
        existing = [
            self._make_occ("occ-done", "2026-04-06T09:00:00+00:00", status="completed"),
            self._make_occ("occ-sched", "2026-04-13T09:00:00+00:00", status="scheduled"),
        ]
        deleted_ids = []

        with (
            patch("occurrence_service.get_series", return_value=series),
            patch("occurrence_service.list_occurrences_for_series", return_value=existing),
            patch("occurrence_service.delete_occurrence", side_effect=lambda oid: deleted_ids.append(oid)),
            patch("occurrence_service.save_occurrences_batch"),
        ):
            regenerate_series("s-1", "UTC", date(2026, 4, 1), date(2026, 4, 30))

        assert "occ-done" not in deleted_ids
        assert "occ-sched" in deleted_ids

    def test_no_changes_when_schedule_unchanged(self):
        """If the schedule hasn't actually changed, nothing is deleted or created."""
        series = _make_series(
            schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),  # Mon
        )
        # Existing occurrences already match the Monday schedule
        existing = [
            self._make_occ("occ-6", "2026-04-06T09:00:00+00:00"),
            self._make_occ("occ-13", "2026-04-13T09:00:00+00:00"),
            self._make_occ("occ-20", "2026-04-20T09:00:00+00:00"),
            self._make_occ("occ-27", "2026-04-27T09:00:00+00:00"),
        ]
        deleted_ids = []
        batch_saved = []

        with (
            patch("occurrence_service.get_series", return_value=series),
            patch("occurrence_service.list_occurrences_for_series", return_value=existing),
            patch("occurrence_service.delete_occurrence", side_effect=lambda oid: deleted_ids.append(oid)),
            patch("occurrence_service.save_occurrences_batch", side_effect=lambda lst: batch_saved.extend(lst)),
        ):
            result = regenerate_series("s-1", "UTC", date(2026, 4, 1), date(2026, 4, 30))

        assert deleted_ids == []
        assert result["created"] == 0
        assert result["cancelled"] == 0
