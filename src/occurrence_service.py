"""Occurrence generation service.

Bridges the pure recurrence engine (recurrence.py) and Firestore storage
(series_storage.py).  Provides the high-level operations:

- generate_and_save: expand a Series into Occurrence documents for a date window
- apply_override:    update a single Occurrence (skip/reschedule/edit-one)
- regenerate_series: idempotent re-expansion after a Series rule change
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from models import (
    Occurrence,
    OccurrenceOverrides,
    OccurrenceStatus,
    Series,
)
from recurrence import generate_occurrences
from series_storage import (
    get_series,
    list_occurrences_for_series,
    save_occurrence,
    save_occurrences_batch,
    update_occurrence,
)


def _to_workspace_tz(series: Series, workspace_timezone: str) -> ZoneInfo:
    return ZoneInfo(workspace_timezone)


# ---------------------------------------------------------------------------
# Core: generate and persist Occurrences for a Series window
# ---------------------------------------------------------------------------

def generate_and_save(
    series: Series,
    workspace_timezone: str,
    start_date: date,
    end_date: date,
) -> list[Occurrence]:
    """Expand *series* into Occurrence documents for [start_date, end_date].

    Only creates documents that don't already exist (idempotent within the
    window). Already-existing occurrences (by scheduled_for) are left
    untouched so that overrides and status changes are preserved.

    Returns the list of *newly created* Occurrence objects.
    """
    tz = _to_workspace_tz(series, workspace_timezone)

    # Generate candidate UTC datetimes
    utc_datetimes = generate_occurrences(
        rule=series.schedule_rule,
        default_time=series.default_time,
        timezone=tz,
        start_date=start_date,
        end_date=end_date,
    )

    if not utc_datetimes:
        return []

    # Load existing occurrences so we can skip already-created ones
    existing = list_occurrences_for_series(series.series_id)
    existing_times: set[str] = {occ.scheduled_for for occ in existing}
    existing_count = len(existing)

    new_occurrences: list[Occurrence] = []
    for idx, utc_dt in enumerate(utc_datetimes):
        scheduled_for = utc_dt.isoformat()
        if scheduled_for in existing_times:
            continue
        occ = Occurrence(
            occurrence_id=str(uuid.uuid4()),
            series_id=series.series_id,
            workspace_id=series.workspace_id,
            scheduled_for=scheduled_for,
            status="scheduled",
            sequence_index=existing_count + len(new_occurrences),
        )
        new_occurrences.append(occ)

    if new_occurrences:
        save_occurrences_batch(new_occurrences)

    return new_occurrences


# ---------------------------------------------------------------------------
# Override operations on individual Occurrences
# ---------------------------------------------------------------------------

def skip_occurrence(occurrence_id: str) -> Occurrence:
    """Mark a single Occurrence as cancelled (skip it)."""
    return _set_status(occurrence_id, "cancelled")


def complete_occurrence(occurrence_id: str) -> Occurrence:
    """Mark a single Occurrence as completed."""
    return _set_status(occurrence_id, "completed")


def reschedule_occurrence(
    occurrence_id: str,
    new_scheduled_for: str,
    *,
    new_time: str | None = None,
) -> Occurrence:
    """Reschedule a single Occurrence to a new datetime.

    Args:
        occurrence_id:   The occurrence to change.
        new_scheduled_for: New ISO 8601 UTC datetime string.
        new_time:        Optional override for wall-clock time display.
    """
    updates: dict = {
        "scheduled_for": new_scheduled_for,
        "status": "rescheduled",
    }
    return update_occurrence(occurrence_id, updates)


def edit_occurrence(
    occurrence_id: str,
    overrides: OccurrenceOverrides,
) -> Occurrence:
    """Apply field-level overrides to a single Occurrence.

    This is "edit this one instance" — the series is unchanged.
    """
    return update_occurrence(
        occurrence_id,
        {"overrides": overrides.to_dict()},
    )


# ---------------------------------------------------------------------------
# Idempotent series regeneration
# ---------------------------------------------------------------------------

def regenerate_series(
    series_id: str,
    workspace_timezone: str,
    start_date: date,
    end_date: date,
) -> dict:
    """Re-expand a Series after its rule changes, preserving overrides.

    Strategy:
    - Fetch fresh series from Firestore.
    - For occurrences in [start_date, end_date] that are still in "scheduled"
      state and whose scheduled_for no longer matches the new rule, cancel them.
    - Generate new occurrences for the window, skipping any that already exist.

    Returns a summary dict: {"created": int, "cancelled": int}.
    """
    series = get_series(series_id)
    if series is None:
        raise ValueError(f"Series not found: {series_id}")

    tz = _to_workspace_tz(series, workspace_timezone)

    # New canonical datetimes from the updated rule
    new_utc_times = generate_occurrences(
        rule=series.schedule_rule,
        default_time=series.default_time,
        timezone=tz,
        start_date=start_date,
        end_date=end_date,
    )
    new_time_set: set[str] = {dt.isoformat() for dt in new_utc_times}

    existing = list_occurrences_for_series(series_id)
    cancelled = 0
    existing_times: set[str] = set()

    for occ in existing:
        existing_times.add(occ.scheduled_for)
        # Only auto-cancel scheduled occurrences that are no longer in the rule
        if (
            occ.status == "scheduled"
            and occ.scheduled_for not in new_time_set
            and _in_window(occ.scheduled_for, start_date, end_date, tz)
        ):
            update_occurrence(occ.occurrence_id, {"status": "cancelled"})
            cancelled += 1

    # Create new occurrences for times not yet in Firestore
    to_create: list[Occurrence] = []
    base_seq = len(existing)
    for idx, utc_dt in enumerate(new_utc_times):
        scheduled_for = utc_dt.isoformat()
        if scheduled_for not in existing_times:
            to_create.append(Occurrence(
                occurrence_id=str(uuid.uuid4()),
                series_id=series_id,
                workspace_id=series.workspace_id,
                scheduled_for=scheduled_for,
                status="scheduled",
                sequence_index=base_seq + idx,
            ))

    if to_create:
        save_occurrences_batch(to_create)

    return {"created": len(to_create), "cancelled": cancelled}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_status(occurrence_id: str, status: OccurrenceStatus) -> Occurrence:
    return update_occurrence(occurrence_id, {"status": status})


def _in_window(
    scheduled_for: str, start_date: date, end_date: date, tz: ZoneInfo
) -> bool:
    """Return True if scheduled_for falls within [start_date, end_date] local."""
    try:
        utc_dt = datetime.fromisoformat(scheduled_for)
    except ValueError:
        return False
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    local_date = utc_dt.astimezone(tz).date()
    return start_date <= local_date <= end_date
