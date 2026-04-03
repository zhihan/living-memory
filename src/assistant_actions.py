"""Assistant actions — definitions and execution for the Meeting Organizer Assistant.

Each action follows the preview/confirm pattern:
  1. The assistant proposes an action (stored as pending_action in Firestore).
  2. The user confirms via /v2/assistant/actions/{id}/confirm.
  3. On confirmation, execute() is called.

Action types: create_series, create_occurrence, reschedule_occurrence,
              draft_material, generate_reminder_text
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)



ActionType = Literal[
    "create_series",
    "create_occurrence",
    "reschedule_occurrence",
    "draft_material",
    "generate_reminder_text",
    "update_occurrence_notes",
    "update_occurrence",
    "update_room",
    "update_series",
]

ActionStatus = Literal["pending", "confirmed", "cancelled", "executed", "failed"]

PENDING_ACTIONS_COLLECTION = "pending_assistant_actions"
ACTION_TTL_SECONDS = 600  # 10 minutes


@dataclass
class PendingAction:
    """A proposed but not-yet-confirmed assistant action."""

    action_id: str
    room_id: str
    requested_by_uid: str
    action_type: ActionType
    preview_summary: str
    payload: dict[str, Any]
    status: ActionStatus = "pending"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "room_id": self.room_id,
            "requested_by_uid": self.requested_by_uid,
            "action_type": self.action_type,
            "preview_summary": self.preview_summary,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at,
            "executed_at": self.executed_at,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PendingAction":
        return cls(
            action_id=data["action_id"],
            room_id=data.get("room_id") or data.get("workspace_id", ""),
            requested_by_uid=data["requested_by_uid"],
            action_type=data["action_type"],
            preview_summary=data["preview_summary"],
            payload=dict(data.get("payload", {})),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
            executed_at=data.get("executed_at"),
            result=data.get("result"),
            error=data.get("error"),
        )


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------

def save_pending_action(action: PendingAction) -> str:
    """Persist a PendingAction to Firestore and return the action_id."""
    from db import get_client as _get_client
    db = _get_client()
    db.collection(PENDING_ACTIONS_COLLECTION).document(action.action_id).set(
        action.to_dict()
    )
    return action.action_id


def get_pending_action(action_id: str) -> "PendingAction | None":
    """Fetch a PendingAction from Firestore, or None if not found / expired."""
    from db import get_client as _get_client
    db = _get_client()
    doc = db.collection(PENDING_ACTIONS_COLLECTION).document(action_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    action = PendingAction.from_dict(data)
    created = action.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age > ACTION_TTL_SECONDS:
        logger.info("PendingAction %s expired (age=%.0fs)", action_id, age)
        return None
    return action


def update_pending_action_status(
    action_id: str,
    status: ActionStatus,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """Update status fields on an existing PendingAction document."""
    from db import get_client as _get_client
    db = _get_client()
    updates: dict[str, Any] = {"status": status}
    if result is not None:
        updates["result"] = result
    if error is not None:
        updates["error"] = error
    if status in ("executed", "failed"):
        updates["executed_at"] = datetime.now(timezone.utc)
    db.collection(PENDING_ACTIONS_COLLECTION).document(action_id).update(updates)


# ---------------------------------------------------------------------------
# CreateSeriesAction
# ---------------------------------------------------------------------------

def build_create_series_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    title = payload.get("title", "New Meeting")
    freq = payload.get("schedule_rule", {}).get("frequency", "weekly")
    time_str = payload.get("default_time", "")
    at_time = f" at {time_str}" if time_str else ""
    summary = (
        f'Create a new {freq} series titled "{title}"{at_time}'
        f' in room {room_id}.'
    )
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="create_series",
        preview_summary=summary,
        payload=payload,
    )


def execute_create_series(action: PendingAction) -> dict:
    import series_storage
    import room_storage
    from models import Series, ScheduleRule

    payload = action.payload
    rm = room_storage.get_room(action.room_id)
    if rm is None:
        raise ValueError(f"Room not found: {action.room_id}")

    series = Series(
        series_id=str(uuid.uuid4()),
        room_id=action.room_id,
        kind=payload.get("kind", "meeting"),
        title=payload["title"],
        schedule_rule=ScheduleRule.from_dict(
            payload.get("schedule_rule", {"frequency": "weekly"})
        ),
        default_time=payload.get("default_time"),
        default_duration_minutes=payload.get("default_duration_minutes"),
        default_location=payload.get("default_location"),
        default_online_link=payload.get("default_online_link"),
        description=payload.get("description"),
        created_by=action.requested_by_uid,
    )
    series_storage.create_series(series)
    logger.info(
        "Created series %s via assistant action %s",
        series.series_id,
        action.action_id,
    )
    return {"created": "series", "series": series.to_dict()}


# ---------------------------------------------------------------------------
# CreateOccurrenceAction
# ---------------------------------------------------------------------------

def build_create_occurrence_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    series_id = payload.get("series_id", "?")
    scheduled_for = payload.get("scheduled_for", "?")
    host = payload.get("host")
    notes = payload.get("notes")
    parts = [f"Create a new occurrence in series {series_id} on {scheduled_for}"]
    if host:
        parts.append(f"hosted by {host}")
    if notes:
        preview = notes[:60]
        parts.append(f'with agenda "{preview}"')
    summary = ", ".join(parts) + "."
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="create_occurrence",
        preview_summary=summary,
        payload=payload,
    )


def execute_create_occurrence(action: PendingAction) -> dict:
    from models import OccurrenceOverrides
    from occurrence_service import create_single_occurrence

    payload = action.payload
    series_id = payload["series_id"]

    # Build overrides from notes if provided
    overrides = None
    notes = payload.get("notes")
    if notes:
        overrides = OccurrenceOverrides(notes=notes)

    occ = create_single_occurrence(
        series_id=series_id,
        scheduled_for=payload["scheduled_for"],
        host=payload.get("host"),
        location=payload.get("location"),
        overrides=overrides,
    )
    logger.info(
        "Created occurrence %s via assistant action %s",
        occ.occurrence_id,
        action.action_id,
    )
    return {"created": "occurrence", "occurrence": occ.to_dict()}


# ---------------------------------------------------------------------------
# RescheduleOccurrenceAction
# ---------------------------------------------------------------------------

def build_reschedule_occurrence_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    occ_id = payload.get("occurrence_id", "?")
    new_dt = payload.get("new_scheduled_for", "?")
    summary = f"Reschedule occurrence {occ_id} to {new_dt}."
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="reschedule_occurrence",
        preview_summary=summary,
        payload=payload,
    )


def execute_reschedule_occurrence(action: PendingAction) -> dict:
    from occurrence_service import reschedule_occurrence

    payload = action.payload
    updated = reschedule_occurrence(
        payload["occurrence_id"], payload["new_scheduled_for"]
    )
    logger.info(
        "Rescheduled occurrence %s via assistant action %s",
        payload["occurrence_id"],
        action.action_id,
    )
    return {"rescheduled": "occurrence", "occurrence": updated.to_dict()}


# ---------------------------------------------------------------------------
# DraftMaterialAction
# ---------------------------------------------------------------------------

def build_draft_material_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    kind = payload.get("material_kind", "agenda")
    title = payload.get("title", "Untitled")
    summary = f'Draft a {kind} for "{title}".'
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="draft_material",
        preview_summary=summary,
        payload=payload,
    )


def execute_draft_material(action: PendingAction) -> dict:
    payload = action.payload
    logger.info("Confirmed draft material via assistant action %s", action.action_id)
    return {
        "material_kind": payload.get("material_kind", "agenda"),
        "title": payload.get("title", ""),
        "draft_text": payload.get("draft_text", ""),
    }


# ---------------------------------------------------------------------------
# GenerateReminderTextAction
# ---------------------------------------------------------------------------

def build_generate_reminder_text_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    ref = payload.get("occurrence_id") or payload.get("series_id") or "?"
    summary = f"Generate a shareable reminder message for {ref}."
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="generate_reminder_text",
        preview_summary=summary,
        payload=payload,
    )


def execute_generate_reminder_text(action: PendingAction) -> dict:
    payload = action.payload
    logger.info("Confirmed reminder text via assistant action %s", action.action_id)
    return {
        "reminder_text": payload.get("reminder_text", ""),
        "occurrence_id": payload.get("occurrence_id"),
        "series_id": payload.get("series_id"),
    }


# ---------------------------------------------------------------------------
# UpdateOccurrenceNotesAction (DEPRECATED — use update_occurrence instead)
# Kept for backwards compatibility with pending actions already in Firestore.
# ---------------------------------------------------------------------------

def build_update_occurrence_notes_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    occ_id = payload.get("occurrence_id", "?")
    notes_preview = (payload.get("notes") or "")[:80]
    summary = f'Update agenda/notes for occurrence {occ_id}: "{notes_preview}"'
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="update_occurrence_notes",
        preview_summary=summary,
        payload=payload,
    )


def execute_update_occurrence_notes(action: PendingAction) -> dict:
    import series_storage

    payload = action.payload
    occ_id = payload["occurrence_id"]
    notes = payload.get("notes", "")

    occ = series_storage.get_occurrence(occ_id)
    if occ is None:
        raise ValueError(f"Occurrence not found: {occ_id}")

    overrides = occ.overrides.to_dict() if occ.overrides else {}
    overrides["notes"] = notes
    series_storage.update_occurrence(occ_id, {"overrides": overrides})

    logger.info(
        "Updated notes for occurrence %s via assistant action %s",
        occ_id,
        action.action_id,
    )
    return {"updated": "occurrence_notes", "occurrence_id": occ_id, "notes": notes}


# ---------------------------------------------------------------------------
# UpdateOccurrenceAction (general: host, location, notes, etc.)
# ---------------------------------------------------------------------------

def build_update_occurrence_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    occ_id = payload.get("occurrence_id", "?")
    changes: list[str] = []
    if payload.get("host"):
        changes.append(f'host to "{payload["host"]}"')
    if payload.get("location"):
        changes.append(f'location to "{payload["location"]}"')
    if payload.get("notes"):
        preview = payload["notes"][:60]
        changes.append(f'notes to "{preview}"')
    if payload.get("links") is not None:
        n = len(payload["links"])
        changes.append(f'{n} resource link{"s" if n != 1 else ""}')
    detail = ", ".join(changes) if changes else "fields"
    summary = f"Update {detail} for occurrence {occ_id}."
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="update_occurrence",
        preview_summary=summary,
        payload=payload,
    )


def execute_update_occurrence(action: PendingAction) -> dict:
    import series_storage

    payload = action.payload
    occ_id = payload["occurrence_id"]

    occ = series_storage.get_occurrence(occ_id)
    if occ is None:
        raise ValueError(f"Occurrence not found: {occ_id}")

    updates: dict = {}
    if "host" in payload:
        updates["host"] = payload["host"]
    if "location" in payload:
        updates["location"] = payload["location"]
    if "notes" in payload:
        overrides = occ.overrides.to_dict() if occ.overrides else {}
        overrides["notes"] = payload["notes"]
        updates["overrides"] = overrides
    if "links" in payload:
        updates["links"] = payload["links"]

    if updates:
        series_storage.update_occurrence(occ_id, updates)

    logger.info(
        "Updated occurrence %s via assistant action %s",
        occ_id,
        action.action_id,
    )
    return {"updated": "occurrence", "occurrence_id": occ_id, "fields": list(updates.keys())}


# ---------------------------------------------------------------------------
# UpdateRoomAction
# ---------------------------------------------------------------------------

_UPDATE_ROOM_FIELDS = {"title", "timezone", "description", "links"}


def build_update_room_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    changes: list[str] = []
    if payload.get("title"):
        changes.append(f'title to "{payload["title"]}"')
    if payload.get("timezone"):
        changes.append(f'timezone to "{payload["timezone"]}"')
    if payload.get("description") is not None:
        changes.append("description")
    if payload.get("links") is not None:
        n = len(payload["links"])
        changes.append(f'{n} resource link{"s" if n != 1 else ""}')
    detail = ", ".join(changes) if changes else "fields"
    summary = f"Update {detail} on room {room_id}."
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="update_room",
        preview_summary=summary,
        payload=payload,
    )


def execute_update_room(action: PendingAction) -> dict:
    import room_storage

    payload = action.payload
    updates = {k: v for k, v in payload.items() if k in _UPDATE_ROOM_FIELDS}

    if updates:
        room_storage.update_room(action.room_id, updates)

    logger.info(
        "Updated room %s via assistant action %s",
        action.room_id,
        action.action_id,
    )
    return {"updated": "room", "room_id": action.room_id, "fields": list(updates.keys())}


# ---------------------------------------------------------------------------
# UpdateSeriesAction
# ---------------------------------------------------------------------------

_UPDATE_SERIES_FIELDS = {
    "title", "kind", "description", "default_time", "default_duration_minutes",
    "default_location", "default_online_link", "location_type", "enable_done",
    "links",
}


def build_update_series_action(
    room_id: str, uid: str, payload: dict
) -> PendingAction:
    series_id = payload.get("series_id", "?")
    changes: list[str] = []
    if payload.get("title"):
        changes.append(f'title to "{payload["title"]}"')
    if payload.get("description") is not None:
        changes.append("description")
    if payload.get("default_time"):
        changes.append(f'time to {payload["default_time"]}')
    if payload.get("default_duration_minutes"):
        changes.append(f'duration to {payload["default_duration_minutes"]}min')
    if payload.get("default_location"):
        changes.append(f'location to "{payload["default_location"]}"')
    if payload.get("default_online_link"):
        changes.append("online link")
    if payload.get("links") is not None:
        n = len(payload["links"])
        changes.append(f'{n} resource link{"s" if n != 1 else ""}')
    detail = ", ".join(changes) if changes else "fields"
    summary = f"Update {detail} on series {series_id}."
    return PendingAction(
        action_id=str(uuid.uuid4()),
        room_id=room_id,
        requested_by_uid=uid,
        action_type="update_series",
        preview_summary=summary,
        payload=payload,
    )


def execute_update_series(action: PendingAction) -> dict:
    import series_storage

    payload = action.payload
    series_id = payload["series_id"]
    updates = {k: v for k, v in payload.items() if k in _UPDATE_SERIES_FIELDS}

    if updates:
        series_storage.update_series(series_id, updates)

    logger.info(
        "Updated series %s via assistant action %s",
        series_id,
        action.action_id,
    )
    return {"updated": "series", "series_id": series_id, "fields": list(updates.keys())}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def execute_action(action: PendingAction) -> dict:
    """Dispatch to the correct execute function based on action.action_type."""
    dispatch = {
        "create_series": execute_create_series,
        "create_occurrence": execute_create_occurrence,
        "reschedule_occurrence": execute_reschedule_occurrence,
        "draft_material": execute_draft_material,
        "generate_reminder_text": execute_generate_reminder_text,
        "update_occurrence_notes": execute_update_occurrence_notes,
        "update_occurrence": execute_update_occurrence,
        "update_room": execute_update_room,
        "update_series": execute_update_series,
    }
    fn = dispatch.get(action.action_type)
    if fn is None:
        raise ValueError(f"Unknown action type: {action.action_type}")
    return fn(action)
