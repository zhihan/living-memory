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


def _get_rotation_host(series: Series, sequence_index: int) -> str | None:
    """Return the host label for this occurrence based on rotation."""
    if not series.host_rotation or series.rotation_mode in ("none", "manual"):
        return None
    return series.host_rotation[sequence_index % len(series.host_rotation)]


def _to_room_tz(series: Series, room_timezone: str) -> ZoneInfo:
    return ZoneInfo(room_timezone)


# ---------------------------------------------------------------------------
# Core: generate and persist Occurrences for a Series window
# ---------------------------------------------------------------------------

def generate_and_save(
    series: Series,
    room_timezone: str,
    start_date: date,
    end_date: date,
) -> list[Occurrence]:
    """Expand *series* into Occurrence documents for [start_date, end_date].

    Only creates documents that don't already exist (idempotent within the
    window). Already-existing occurrences (by scheduled_for) are left
    untouched so that overrides and status changes are preserved.

    Returns the list of *newly created* Occurrence objects.
    """
    tz = _to_room_tz(series, room_timezone)

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
        seq = existing_count + len(new_occurrences)

        # Determine host from rotation
        host_label = _get_rotation_host(series, seq)

        # Determine location
        if series.location_type == "none":
            loc = None
        elif series.rotation_mode == "host_and_location" and host_label:
            # Look up host's address in the map, fall back to default
            loc = (series.host_addresses or {}).get(host_label) or series.default_location
        elif series.location_type == "fixed":
            loc = series.default_location
        else:
            loc = None

        occ = Occurrence(
            occurrence_id=str(uuid.uuid4()),
            series_id=series.series_id,
            room_id=series.room_id,
            scheduled_for=scheduled_for,
            status="scheduled",
            location=loc,
            host=host_label,
            sequence_index=seq,
            enable_check_in=series.enable_done,
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

    This is "edit this one instance" -- the series is unchanged.
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
    room_timezone: str,
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

    tz = _to_room_tz(series, room_timezone)

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
            seq = base_seq + idx
            if series.location_type == "none":
                loc = None
            elif series.location_type == "fixed":
                loc = series.default_location
            else:
                loc = None
            to_create.append(Occurrence(
                occurrence_id=str(uuid.uuid4()),
                series_id=series_id,
                room_id=series.room_id,
                scheduled_for=scheduled_for,
                status="scheduled",
                location=loc,
                sequence_index=seq,
                enable_check_in=series.enable_done,
            ))

    if to_create:
        save_occurrences_batch(to_create)

    return {"created": len(to_create), "cancelled": cancelled}


# ---------------------------------------------------------------------------
# Re-apply check-in days to upcoming occurrences
# ---------------------------------------------------------------------------

def apply_check_in_days(series_id: str) -> int:
    """Set enable_check_in on all future 'scheduled' occurrences
    based on the series' enable_done flag.  Returns the count updated."""
    series = get_series(series_id)
    if series is None:
        raise ValueError(f"Series not found: {series_id}")

    should_enable = series.enable_done

    existing = list_occurrences_for_series(series_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    future = [
        o for o in existing
        if o.status == "scheduled" and o.scheduled_for >= now_iso
    ]

    updated = 0
    for occ in future:
        if occ.enable_check_in != should_enable:
            update_occurrence(occ.occurrence_id, {"enable_check_in": should_enable})
            updated += 1
    return updated


# ---------------------------------------------------------------------------
# Rotation regeneration
# ---------------------------------------------------------------------------

def regenerate_rotation_from_occurrence(
    series_id: str,
    occurrence_id: str,
) -> dict:
    """Re-apply rotation to subsequent occurrences, continuing from the given occurrence's host.

    Use case: User manually fixes one occurrence's host, then wants all following
    occurrences to continue the rotation pattern from that point.

    Returns: {"updated_count": int, "starting_index": int, "message": str, "warnings": list[str]}
    """
    series = get_series(series_id)
    if series is None:
        raise ValueError(f"Series not found: {series_id}")

    if series.rotation_mode in ("none", "manual") or not series.host_rotation:
        raise ValueError("Series has no rotation configured")

    # Get the target occurrence
    from series_storage import get_occurrence as _get_occurrence
    target_occ = _get_occurrence(occurrence_id)
    if target_occ is None:
        raise ValueError(f"Occurrence not found: {occurrence_id}")

    # Find the target occurrence's host in the rotation list
    current_host = target_occ.host
    if not current_host:
        raise ValueError("Target occurrence has no host set")

    try:
        starting_index = series.host_rotation.index(current_host)
        warnings = []
    except ValueError:
        # Host not in rotation list - still allow regeneration, start from beginning
        starting_index = 0
        warnings = [f"Host '{current_host}' not found in rotation list. Starting from beginning."]

    # Get all subsequent scheduled occurrences
    all_occs = list_occurrences_for_series(series_id)
    all_occs.sort(key=lambda o: o.scheduled_for)

    # Find occurrences after the target
    target_idx = next((i for i, o in enumerate(all_occs) if o.occurrence_id == occurrence_id), None)
    if target_idx is None:
        raise ValueError("Could not locate target occurrence in series")

    subsequent = [
        o for o in all_occs[target_idx + 1:]
        if o.status == "scheduled"
    ]

    if not subsequent:
        return {
            "updated_count": 0,
            "starting_index": starting_index,
            "message": "No subsequent scheduled occurrences to update",
            "warnings": warnings,
        }

    # Re-assign hosts (and locations if needed) starting from next position in rotation
    rotation_len = len(series.host_rotation)
    updated_count = 0

    for i, occ in enumerate(subsequent):
        # Next position in rotation (starting_index + 1 for first, +2 for second, etc.)
        rotation_position = (starting_index + 1 + i) % rotation_len
        new_host = series.host_rotation[rotation_position]

        updates: dict = {"host": new_host}

        # Update location if in host_and_location mode
        if series.rotation_mode == "host_and_location":
            new_location = (series.host_addresses or {}).get(new_host) or series.default_location
            updates["location"] = new_location

        update_occurrence(occ.occurrence_id, updates)
        updated_count += 1

    return {
        "updated_count": updated_count,
        "starting_index": starting_index,
        "message": f"Updated {updated_count} occurrence(s) continuing rotation from '{current_host}'",
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def create_single_occurrence(
    series_id: str,
    scheduled_for: str,
    *,
    location: str | None = None,
    host: str | None = None,
    enable_check_in: bool | None = None,
    overrides: OccurrenceOverrides | None = None,
) -> Occurrence:
    """Create a single new Occurrence in a series and re-index sequence order.

    The new occurrence is inserted at the correct chronological position
    based on ``scheduled_for`` and all sequence_index values in the series
    are recalculated so that they reflect sorted order.
    """
    series = get_series(series_id)
    if series is None:
        raise ValueError(f"Series not found: {series_id}")

    # Default enable_check_in from the series if not explicitly provided
    if enable_check_in is None:
        enable_check_in = series.enable_done

    # Default location from series if not provided
    if location is None and series.location_type == "fixed":
        location = series.default_location

    occ = Occurrence(
        occurrence_id=str(uuid.uuid4()),
        series_id=series_id,
        room_id=series.room_id,
        scheduled_for=scheduled_for,
        status="scheduled",
        location=location,
        host=host,
        overrides=overrides,
        enable_check_in=enable_check_in,
    )
    save_occurrence(occ)

    # Re-index all occurrences in the series by scheduled_for order
    all_occs = list_occurrences_for_series(series_id)
    all_occs.sort(key=lambda o: o.scheduled_for)
    for idx, o in enumerate(all_occs):
        if o.sequence_index != idx:
            update_occurrence(o.occurrence_id, {"sequence_index": idx})

    # Return the occurrence with its final sequence_index
    for o in all_occs:
        if o.occurrence_id == occ.occurrence_id:
            occ.sequence_index = all_occs.index(o)
            break

    return occ


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
