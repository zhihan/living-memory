"""Tests for rotation modes feature (#115)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import Occurrence, ScheduleRule, Series
from occurrence_service import (
    _get_rotation_host,
    generate_and_save,
    regenerate_rotation_from_occurrence,
)


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Test _get_rotation_host()
# ---------------------------------------------------------------------------

def test_get_rotation_host_none_mode():
    """When rotation_mode is 'none', host should be None."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        rotation_mode="none",
        host_rotation=["Alice", "Bob"],
    )
    assert _get_rotation_host(series, 0) is None
    assert _get_rotation_host(series, 1) is None


def test_get_rotation_host_no_rotation_list():
    """When host_rotation is empty, host should be None."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        rotation_mode="host_only",
        host_rotation=None,
    )
    assert _get_rotation_host(series, 0) is None


def test_get_rotation_host_cycles():
    """Host should cycle through the rotation list."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        rotation_mode="host_only",
        host_rotation=["Alice", "Bob", "Carol"],
    )
    assert _get_rotation_host(series, 0) == "Alice"
    assert _get_rotation_host(series, 1) == "Bob"
    assert _get_rotation_host(series, 2) == "Carol"
    assert _get_rotation_host(series, 3) == "Alice"  # cycles back
    assert _get_rotation_host(series, 4) == "Bob"


# ---------------------------------------------------------------------------
# Test generate_and_save() with rotation
# ---------------------------------------------------------------------------

@patch("occurrence_service.list_occurrences_for_series")
@patch("occurrence_service.save_occurrences_batch")
def test_generate_and_save_host_only(mock_save, mock_list):
    """Host-only mode assigns hosts without changing location."""
    mock_list.return_value = []  # no existing occurrences

    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),  # Mondays
        default_time="09:00",
        default_location="Office",
        rotation_mode="host_only",
        host_rotation=["Team A", "Team B"],
    )

    new_occs = generate_and_save(
        series,
        workspace_timezone="UTC",
        start_date=date(2026, 4, 6),  # Monday
        end_date=date(2026, 4, 20),
    )

    assert len(new_occs) == 3  # 3 Mondays in the range
    assert new_occs[0].host == "Team A"
    assert new_occs[1].host == "Team B"
    assert new_occs[2].host == "Team A"  # cycles
    # Location should be the default for all
    assert all(occ.location == "Office" for occ in new_occs)


@patch("occurrence_service.list_occurrences_for_series")
@patch("occurrence_service.save_occurrences_batch")
def test_generate_and_save_host_and_location(mock_save, mock_list):
    """Host-and-location mode assigns hosts and looks up their addresses."""
    mock_list.return_value = []

    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),  # Mondays
        default_time="09:00",
        default_location="Office",
        rotation_mode="host_and_location",
        host_rotation=["Alice", "Bob"],
        host_addresses={"Alice": "123 Main St", "Bob": "456 Oak Ave"},
    )

    new_occs = generate_and_save(
        series,
        workspace_timezone="UTC",
        start_date=date(2026, 4, 6),
        end_date=date(2026, 4, 13),
    )

    assert len(new_occs) == 2
    assert new_occs[0].host == "Alice"
    assert new_occs[0].location == "123 Main St"
    assert new_occs[1].host == "Bob"
    assert new_occs[1].location == "456 Oak Ave"


@patch("occurrence_service.list_occurrences_for_series")
@patch("occurrence_service.save_occurrences_batch")
def test_generate_and_save_missing_address_fallback(mock_save, mock_list):
    """Missing address falls back to default_location."""
    mock_list.return_value = []

    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        default_time="09:00",
        default_location="Office",
        rotation_mode="host_and_location",
        host_rotation=["Alice", "Bob"],
        host_addresses={"Alice": "123 Main St"},  # Bob has no address
    )

    new_occs = generate_and_save(
        series,
        workspace_timezone="UTC",
        start_date=date(2026, 4, 6),
        end_date=date(2026, 4, 13),
    )

    assert new_occs[0].location == "123 Main St"  # Alice has address
    assert new_occs[1].location == "Office"  # Bob falls back


# ---------------------------------------------------------------------------
# Test regenerate_rotation_from_occurrence()
# ---------------------------------------------------------------------------

@patch("occurrence_service.get_series")
@patch("series_storage.get_occurrence")
@patch("occurrence_service.list_occurrences_for_series")
@patch("occurrence_service.update_occurrence")
def test_regenerate_rotation_from_occurrence(
    mock_update, mock_list, mock_get_occ, mock_get_series
):
    """Regeneration continues rotation from the target occurrence's host."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        rotation_mode="host_only",
        host_rotation=["A", "B", "C"],
    )
    mock_get_series.return_value = series

    # Target occurrence has host "C" (index 2)
    target = Occurrence(
        occurrence_id="occ-3",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-20T09:00:00+00:00",
        host="C",
    )
    mock_get_occ.return_value = target

    # Subsequent occurrences
    occ4 = Occurrence(
        occurrence_id="occ-4",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-27T09:00:00+00:00",
        status="scheduled",
    )
    occ5 = Occurrence(
        occurrence_id="occ-5",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-05-04T09:00:00+00:00",
        status="scheduled",
    )
    mock_list.return_value = [target, occ4, occ5]

    result = regenerate_rotation_from_occurrence("s-1", "occ-3")

    assert result["updated_count"] == 2
    assert result["starting_index"] == 2  # "C" is at index 2
    assert "continuing rotation from 'C'" in result["message"]

    # Verify update calls: after "C" comes "A", then "B"
    calls = mock_update.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0] == "occ-4"
    assert calls[0][0][1]["host"] == "A"
    assert calls[1][0][0] == "occ-5"
    assert calls[1][0][1]["host"] == "B"


@patch("occurrence_service.get_series")
@patch("series_storage.get_occurrence")
@patch("occurrence_service.list_occurrences_for_series")
@patch("occurrence_service.update_occurrence")
def test_regenerate_host_not_in_rotation_warns(
    mock_update, mock_list, mock_get_occ, mock_get_series
):
    """When host not in rotation, warn and start from beginning."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        rotation_mode="host_only",
        host_rotation=["A", "B", "C"],
    )
    mock_get_series.return_value = series

    target = Occurrence(
        occurrence_id="occ-3",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-20T09:00:00+00:00",
        host="X",  # Not in rotation list
    )
    mock_get_occ.return_value = target

    occ4 = Occurrence(
        occurrence_id="occ-4",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-27T09:00:00+00:00",
        status="scheduled",
    )
    mock_list.return_value = [target, occ4]

    result = regenerate_rotation_from_occurrence("s-1", "occ-3")

    assert result["starting_index"] == 0
    assert len(result["warnings"]) == 1
    assert "not found in rotation list" in result["warnings"][0]

    # starting_index=0 means "A", so next host is at index 1 = "B"
    calls = mock_update.call_args_list
    assert calls[0][0][1]["host"] == "B"


@patch("occurrence_service.get_series")
@patch("series_storage.get_occurrence")
@patch("occurrence_service.list_occurrences_for_series")
def test_regenerate_no_subsequent_occurrences(mock_list, mock_get_occ, mock_get_series):
    """When no subsequent occurrences, return 0 updates."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        rotation_mode="host_only",
        host_rotation=["A", "B"],
    )
    mock_get_series.return_value = series

    target = Occurrence(
        occurrence_id="occ-last",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-20T09:00:00+00:00",
        host="A",
    )
    mock_get_occ.return_value = target
    mock_list.return_value = [target]  # No occurrences after target

    result = regenerate_rotation_from_occurrence("s-1", "occ-last")

    assert result["updated_count"] == 0
    assert "No subsequent scheduled occurrences" in result["message"]


@patch("occurrence_service.get_series")
@patch("series_storage.get_occurrence")
@patch("occurrence_service.list_occurrences_for_series")
@patch("occurrence_service.update_occurrence")
def test_regenerate_with_host_and_location(
    mock_update, mock_list, mock_get_occ, mock_get_series
):
    """Regeneration with host_and_location updates both host and location."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        default_location="Office",
        rotation_mode="host_and_location",
        host_rotation=["Alice", "Bob"],
        host_addresses={"Alice": "123 Main", "Bob": "456 Oak"},
    )
    mock_get_series.return_value = series

    target = Occurrence(
        occurrence_id="occ-1",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-06T09:00:00+00:00",
        host="Alice",
    )
    mock_get_occ.return_value = target

    occ2 = Occurrence(
        occurrence_id="occ-2",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-13T09:00:00+00:00",
        status="scheduled",
    )
    mock_list.return_value = [target, occ2]

    result = regenerate_rotation_from_occurrence("s-1", "occ-1")

    # After Alice comes Bob
    calls = mock_update.call_args_list
    assert calls[0][0][1]["host"] == "Bob"
    assert calls[0][0][1]["location"] == "456 Oak"


@patch("occurrence_service.get_series")
def test_regenerate_no_rotation_configured_raises(mock_get_series):
    """Raises ValueError when series has no rotation configured."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        rotation_mode="none",
    )
    mock_get_series.return_value = series

    with pytest.raises(ValueError, match="no rotation configured"):
        regenerate_rotation_from_occurrence("s-1", "occ-1")


@patch("occurrence_service.get_series")
@patch("series_storage.get_occurrence")
def test_regenerate_no_host_set_raises(mock_get_occ, mock_get_series):
    """Raises ValueError when target occurrence has no host."""
    series = Series(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Test",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        rotation_mode="host_only",
        host_rotation=["A", "B"],
    )
    mock_get_series.return_value = series

    target = Occurrence(
        occurrence_id="occ-1",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-06T09:00:00+00:00",
        host=None,  # No host set
    )
    mock_get_occ.return_value = target

    with pytest.raises(ValueError, match="no host set"):
        regenerate_rotation_from_occurrence("s-1", "occ-1")
