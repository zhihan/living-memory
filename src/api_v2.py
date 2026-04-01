"""API v2 — Rooms, Series, Occurrences, and CheckIns.

Mounted at /v2 on the main FastAPI app.  All routes enforce role-based
permissions using the same Firebase Auth token verification as the v1 API.

Route overview:
  POST   /v2/rooms
  GET    /v2/rooms/{room_id}
  PATCH  /v2/rooms/{room_id}
  DELETE /v2/rooms/{room_id}
  GET    /v2/rooms/{room_id}/members
  POST   /v2/rooms/{room_id}/members
  DELETE /v2/rooms/{room_id}/members/{uid}
  POST   /v2/rooms/{room_id}/invites
  POST   /v2/invites/{invite_id}/accept

  POST   /v2/rooms/{room_id}/series
  GET    /v2/rooms/{room_id}/series
  GET    /v2/series/{series_id}
  PATCH  /v2/series/{series_id}
  DELETE /v2/series/{series_id}

  GET    /v2/rooms/{room_id}/occurrences
  GET    /v2/series/{series_id}/occurrences
  POST   /v2/series/{series_id}/occurrences/generate
  GET    /v2/occurrences/{occurrence_id}
  PATCH  /v2/occurrences/{occurrence_id}

  POST   /v2/occurrences/{occurrence_id}/check-ins
  GET    /v2/occurrences/{occurrence_id}/check-ins
  GET    /v2/occurrences/{occurrence_id}/my-check-in
  PATCH  /v2/check-ins/{check_in_id}
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, field_validator

import series_storage
import room_storage
import telegram_storage
from assistant import run_assistant_stream
from assistant_actions import execute_action, get_pending_action, update_pending_action_status
from models import (
    CheckIn,
    MemberRole,
    Occurrence,
    OccurrenceOverrides,
    ScheduleRule,
    Series,
    Room,
    TelegramBotConfig,
    TelegramUserLink,
)
from occurrence_service import (
    complete_occurrence,
    edit_occurrence,
    generate_and_save,
    reschedule_occurrence,
    skip_occurrence,
)

router = APIRouter(prefix="/v2", tags=["v2"])


# ---------------------------------------------------------------------------
# Auth (reuses Firebase token verification pattern from api.py)
# ---------------------------------------------------------------------------

def _verify_firebase_token(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization[len("Bearer "):]
    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        return firebase_auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


def _require_token(authorization: str = Header(...)) -> dict:
    return _verify_firebase_token(authorization)


def _get_room_or_404(room_id: str) -> Room:
    rm = room_storage.get_room(room_id)
    if rm is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")
    return rm


def _get_series_or_404(series_id: str) -> Series:
    s = series_storage.get_series(series_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Series not found: {series_id}")
    return s


def _require_role(room: Room, uid: str, *roles: MemberRole) -> None:
    """Raise 403 unless uid holds one of the required roles in room."""
    actual_role = room.member_roles.get(uid)
    if actual_role not in roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role required: {roles}. You have: {actual_role!r}",
        )


def _require_organizer(room: Room, uid: str) -> None:
    _require_role(room, uid, "organizer")


def _require_member(room: Room, uid: str) -> None:
    """Any room member (any role) may access this resource."""
    if uid not in room.member_roles and uid not in room.owner_uids:
        raise HTTPException(status_code=403, detail="Not a member of this room")


def _get_member_details(member_roles: dict[str, MemberRole]) -> list[dict]:
    """Best-effort Firebase profile lookup for member display names."""
    details: list[dict] = []
    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth

        if not firebase_admin._apps:
            firebase_admin.initialize_app()
    except Exception:
        firebase_auth = None  # type: ignore[assignment]

    for uid, role in member_roles.items():
        display_name = None
        email = None
        if firebase_auth is not None:
            try:
                user = firebase_auth.get_user(uid)
                display_name = user.display_name
                email = user.email
            except Exception:
                pass
        details.append({
            "uid": uid,
            "role": role,
            "display_name": display_name,
            "email": email,
        })
    return details


def _merge_member_details(room: Room) -> list[dict]:
    """Prefer persisted room profiles, with Firebase lookup as fallback."""
    runtime_details = {d["uid"]: d for d in _get_member_details(room.member_roles)}
    merged: list[dict] = []
    for uid, role in room.member_roles.items():
        stored = room.member_profiles.get(uid, {})
        runtime = runtime_details.get(uid, {})
        merged.append({
            "uid": uid,
            "role": role,
            "display_name": stored.get("display_name") or runtime.get("display_name"),
            "email": stored.get("email") or runtime.get("email"),
        })
    return merged


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class ScheduleRuleIn(BaseModel):
    frequency: str
    weekdays: list[int] = []
    interval: int = 1
    until: Optional[str] = None
    count: Optional[int] = None

    @field_validator('weekdays')
    @classmethod
    def validate_weekdays(cls, v):
        """Ensure all weekdays are valid ISO weekday values (1-7)."""
        for day in v:
            if not isinstance(day, int) or day < 1 or day > 7:
                raise ValueError(f"Invalid weekday value: {day}. Must be 1-7 (1=Monday, 7=Sunday)")
        return v

    def to_model(self) -> ScheduleRule:
        until_dt = None
        if self.until:
            until_dt = datetime.fromisoformat(self.until)
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=timezone.utc)
        return ScheduleRule(
            frequency=self.frequency,
            weekdays=self.weekdays,
            interval=self.interval,
            until=until_dt,
            count=self.count,
        )


class CreateRoomRequest(BaseModel):
    title: str
    type: str = "shared"
    timezone: str = "UTC"
    description: Optional[str] = None


class UpdateRoomRequest(BaseModel):
    title: Optional[str] = None
    timezone: Optional[str] = None
    description: Optional[str] = None


class AddMemberRequest(BaseModel):
    uid: str
    role: str = "participant"


class CreateInviteRequest(BaseModel):
    role: str = "participant"
    expires_in_days: int = 7


class CreateSeriesRequest(BaseModel):
    kind: str
    title: str
    schedule_rule: ScheduleRuleIn
    default_time: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    default_location: Optional[str] = None
    default_online_link: Optional[str] = None
    location_type: Optional[str] = None  # "none", "fixed", or "per_occurrence"
    enable_done: Optional[bool] = None
    rotation_mode: str = "none"  # "none", "manual", "host_only", "host_and_location"
    host_rotation: Optional[list[str]] = None
    host_addresses: Optional[dict[str, str]] = None
    description: Optional[str] = None

    @field_validator('location_type')
    @classmethod
    def validate_location_type(cls, v):
        """Reject deprecated 'rotation' location_type."""
        if v == "rotation":
            raise ValueError("location_type 'rotation' is no longer supported. Use 'fixed' or 'per_occurrence'.")
        return v

    @field_validator('host_addresses')
    @classmethod
    def validate_host_addresses(cls, v):
        """Filter out entries with empty keys or values to prevent Firestore errors."""
        if v is None:
            return v
        return {k: v_ for k, v_ in v.items() if k and k.strip()}

    @field_validator('host_rotation')
    @classmethod
    def validate_host_rotation(cls, v, info):
        """Ensure host_rotation is provided when rotation_mode is set."""
        mode = info.data.get('rotation_mode')
        if mode and mode not in ("none", "manual"):
            if not v:
                raise ValueError("host_rotation required when rotation_mode is not 'none'")
            # Ensure all entries are non-empty
            if any(not host or not host.strip() for host in v):
                raise ValueError("All host_rotation entries must be non-empty")
        return v


class UpdateSeriesRequest(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    default_time: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    default_location: Optional[str] = None
    default_online_link: Optional[str] = None
    location_type: Optional[str] = None  # "none", "fixed", or "per_occurrence"
    enable_done: Optional[bool] = None
    rotation_mode: Optional[str] = None  # "none", "manual", "host_only", "host_and_location"
    host_rotation: Optional[list[str]] = None
    host_addresses: Optional[dict[str, str]] = None
    status: Optional[str] = None
    description: Optional[str] = None
    schedule_rule: Optional[ScheduleRuleIn] = None

    @field_validator('location_type')
    @classmethod
    def validate_location_type(cls, v):
        """Reject deprecated 'rotation' location_type."""
        if v == "rotation":
            raise ValueError("location_type 'rotation' is no longer supported. Use 'fixed' or 'per_occurrence'.")
        return v

    @field_validator('host_addresses')
    @classmethod
    def validate_host_addresses(cls, v):
        """Filter out entries with empty keys or values to prevent Firestore errors."""
        if v is None:
            return v
        return {k: v_ for k, v_ in v.items() if k and k.strip()}


class GenerateOccurrencesRequest(BaseModel):
    start_date: str  # ISO date "YYYY-MM-DD"
    end_date: str    # ISO date "YYYY-MM-DD"
    room_timezone: Optional[str] = None  # overrides room default


class OccurrenceOverridesIn(BaseModel):
    time: Optional[str] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    online_link: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None

    def to_model(self) -> OccurrenceOverrides:
        return OccurrenceOverrides(
            time=self.time,
            duration_minutes=self.duration_minutes,
            location=self.location,
            online_link=self.online_link,
            title=self.title,
            notes=self.notes,
        )


class UpdateOccurrenceRequest(BaseModel):
    status: Optional[str] = None
    scheduled_for: Optional[str] = None
    location: Optional[str] = None
    host: Optional[str] = None
    overrides: Optional[OccurrenceOverridesIn] = None
    enable_check_in: Optional[bool] = None


class UpsertCheckInRequest(BaseModel):
    status: str  # "confirmed", "declined", "missed"
    note: Optional[str] = None


class RegisterTelegramBotRequest(BaseModel):
    bot_token: str
    mode: str = "read_only"


class UpdateTelegramBotRequest(BaseModel):
    mode: str


# ---------------------------------------------------------------------------
# Room endpoints
# ---------------------------------------------------------------------------

@router.post("/rooms", status_code=201)
def create_room(
    body: CreateRoomRequest,
    token: dict = Depends(_require_token),
) -> dict:
    """Create a new room. The caller becomes the first organizer."""
    uid = token["uid"]
    rm = Room(
        room_id=str(uuid.uuid4()),
        title=body.title,
        type=body.type,
        timezone=body.timezone,
        owner_uids=[uid],
        member_roles={uid: "organizer"},
        member_profiles={
            uid: {
                "display_name": token.get("name"),
                "email": token.get("email"),
            },
        },
        description=body.description,
    )
    try:
        room_storage.create_room(rm)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return rm.to_dict()


@router.get("/rooms")
def list_rooms(
    token: dict = Depends(_require_token),
) -> dict:
    """Return all rooms where the caller is a member, with series info."""
    uid = token["uid"]
    rooms = room_storage.list_rooms_for_user(uid)
    results = []
    for rm in rooms:
        d = rm.to_dict()
        series = series_storage.list_series_for_room(rm.room_id)
        d["series_count"] = len(series)
        if len(series) == 1:
            d["series_schedule"] = series[0].to_dict().get("schedule_rule")
            d["series_default_time"] = series[0].default_time
        results.append(d)
    return {"rooms": results}


@router.get("/rooms/{room_id}")
def get_room(
    room_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    uid = token["uid"]
    _require_member(rm, uid)
    return rm.to_dict()


@router.patch("/rooms/{room_id}")
def update_room(
    room_id: str,
    body: UpdateRoomRequest,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token["uid"])
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = room_storage.update_room(room_id, updates)
    return updated.to_dict()


@router.delete("/rooms/{room_id}", status_code=204)
def delete_room(
    room_id: str,
    token: dict = Depends(_require_token),
) -> None:
    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token["uid"])
    room_storage.delete_room(room_id)


@router.get("/rooms/{room_id}/members")
def list_members(
    room_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_member(rm, token["uid"])
    return {
        "room_id": room_id,
        "members": rm.member_roles,
        "member_details": _merge_member_details(rm),
    }


@router.post("/rooms/{room_id}/members", status_code=201)
def add_member(
    room_id: str,
    body: AddMemberRequest,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token["uid"])
    updated = room_storage.add_member(room_id, body.uid, body.role)
    return {"room_id": room_id, "uid": body.uid, "role": body.role}


@router.delete("/rooms/{room_id}/members/{uid}", status_code=204)
def remove_member(
    room_id: str,
    uid: str,
    token: dict = Depends(_require_token),
) -> None:
    rm = _get_room_or_404(room_id)
    caller_uid = token["uid"]
    if uid != caller_uid:
        _require_organizer(rm, caller_uid)
    else:
        _require_member(rm, caller_uid)
    try:
        room_storage.remove_member(room_id, uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Invite endpoints
# ---------------------------------------------------------------------------

@router.post("/rooms/{room_id}/invites", status_code=201)
def create_invite(
    room_id: str,
    body: CreateInviteRequest,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token["uid"])
    try:
        invite = room_storage.create_room_invite(
            room_id,
            created_by=token["uid"],
            role=body.role,
            expires_in_days=body.expires_in_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Omit the datetime objects for clean JSON (convert to iso strings)
    return {
        "invite_id": invite["invite_id"],
        "room_id": invite["room_id"],
        "role": invite["role"],
        "created_by": invite["created_by"],
        "expires_at": invite["expires_at"].isoformat(),
    }


@router.post("/invites/{invite_id}/accept", status_code=200)
def accept_invite(
    invite_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    uid = token["uid"]
    try:
        invite = room_storage.accept_room_invite(invite_id, uid)
        room_id = invite.get("room_id") or invite.get("workspace_id")
        room_storage.update_member_profile(
            room_id,
            uid,
            display_name=token.get("name"),
            email=token.get("email"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"accepted": True, "room_id": room_id, "role": invite["role"]}


# ---------------------------------------------------------------------------
# Series endpoints
# ---------------------------------------------------------------------------

@router.post("/rooms/{room_id}/series", status_code=201)
def create_series(
    room_id: str,
    body: CreateSeriesRequest,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_role(rm, token["uid"], "organizer", "teacher")
    series = Series(
        series_id=str(uuid.uuid4()),
        room_id=room_id,
        kind=body.kind,
        title=body.title,
        schedule_rule=body.schedule_rule.to_model(),
        default_time=body.default_time,
        default_duration_minutes=body.default_duration_minutes,
        default_location=body.default_location,
        default_online_link=body.default_online_link,
        location_type=body.location_type or "fixed",
        enable_done=body.enable_done or False,
        rotation_mode="host_only" if (body.location_type == "none" and body.rotation_mode == "host_and_location") else body.rotation_mode,
        host_rotation=body.host_rotation,
        host_addresses=body.host_addresses,
        description=body.description,
        created_by=token["uid"],
    )
    series_storage.create_series(series)
    return series.to_dict()


@router.get("/rooms/{room_id}/series")
def list_series(
    room_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_member(rm, token["uid"])
    all_series = series_storage.list_series_for_room(room_id)
    return {"room_id": room_id, "series": [s.to_dict() for s in all_series]}


@router.get("/series/{series_id}")
def get_series(
    series_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    s = _get_series_or_404(series_id)
    rm = _get_room_or_404(s.room_id)
    _require_member(rm, token["uid"])
    return s.to_dict()


@router.get("/series/{series_id}/check-in-report")
def series_check_in_report(
    series_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    """Return occurrences with check-in enabled and all their check-ins."""
    s = _get_series_or_404(series_id)
    rm = _get_room_or_404(s.room_id)
    _require_role(rm, token["uid"], "organizer", "teacher")
    occurrences = series_storage.list_occurrences_for_series(series_id)
    practice_occs = [o for o in occurrences if o.enable_check_in]
    practice_occs.sort(key=lambda o: o.scheduled_for)
    check_ins = series_storage.list_check_ins_for_series(series_id)
    return {
        "series_id": series_id,
        "occurrences": [o.to_dict() for o in practice_occs],
        "check_ins": [ci.to_dict() for ci in check_ins],
        "members": rm.member_roles,
        "member_profiles": rm.member_profiles,
    }


@router.patch("/series/{series_id}")
def update_series(
    series_id: str,
    body: UpdateSeriesRequest,
    token: dict = Depends(_require_token),
) -> dict:
    s = _get_series_or_404(series_id)
    rm = _get_room_or_404(s.room_id)
    _require_role(rm, token["uid"], "organizer", "teacher")
    updates: dict = {}
    for field in ("kind", "title", "default_time", "default_duration_minutes",
                  "default_location", "default_online_link", "location_type",
                  "enable_done", "rotation_mode",
                  "host_rotation", "host_addresses", "status", "description"):
        val = getattr(body, field)
        if val is not None:
            updates[field] = val
    if body.schedule_rule is not None:
        updates["schedule_rule"] = body.schedule_rule.to_model().to_dict()
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    # Auto-downgrade rotation_mode when location becomes "none"
    effective_location_type = updates.get("location_type", s.location_type)
    effective_rotation_mode = updates.get("rotation_mode", s.rotation_mode)
    if effective_location_type == "none" and effective_rotation_mode == "host_and_location":
        updates["rotation_mode"] = "host_only"
    updated = series_storage.update_series(series_id, updates)
    if "enable_done" in updates:
        from occurrence_service import apply_check_in_days
        apply_check_in_days(series_id)
    return updated.to_dict()


@router.delete("/series/{series_id}", status_code=204)
def delete_series(
    series_id: str,
    token: dict = Depends(_require_token),
) -> None:
    s = _get_series_or_404(series_id)
    rm = _get_room_or_404(s.room_id)
    _require_organizer(rm, token["uid"])
    series_storage.delete_series(series_id)


# ---------------------------------------------------------------------------
# Occurrence endpoints
# ---------------------------------------------------------------------------

@router.post("/series/{series_id}/occurrences/generate", status_code=201)
def generate_occurrences_endpoint(
    series_id: str,
    body: GenerateOccurrencesRequest,
    token: dict = Depends(_require_token),
) -> dict:
    """Expand a Series into Occurrence documents for a date window."""
    s = _get_series_or_404(series_id)
    rm = _get_room_or_404(s.room_id)
    _require_role(rm, token["uid"], "organizer", "teacher")
    try:
        start = date.fromisoformat(body.start_date)
        end = date.fromisoformat(body.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {exc}") from exc
    tz = body.room_timezone or rm.timezone
    new_occs = generate_and_save(s, tz, start, end)
    return {"created": len(new_occs), "occurrences": [o.to_dict() for o in new_occs]}


@router.get("/rooms/{room_id}/occurrences")
def list_room_occurrences(
    room_id: str,
    status: Optional[str] = None,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_member(rm, token["uid"])
    occs = series_storage.list_occurrences_for_room(room_id, status=status)
    return {"room_id": room_id, "occurrences": [o.to_dict() for o in occs]}


@router.get("/series/{series_id}/occurrences")
def list_series_occurrences(
    series_id: str,
    status: Optional[str] = None,
    token: dict = Depends(_require_token),
) -> dict:
    s = _get_series_or_404(series_id)
    rm = _get_room_or_404(s.room_id)
    _require_member(rm, token["uid"])
    occs = series_storage.list_occurrences_for_series(series_id, status=status)
    return {"series_id": series_id, "occurrences": [o.to_dict() for o in occs]}


@router.get("/occurrences/{occurrence_id}")
def get_occurrence(
    occurrence_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    occ = series_storage.get_occurrence(occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    rm = _get_room_or_404(occ.room_id)
    _require_member(rm, token["uid"])
    return occ.to_dict()


@router.patch("/occurrences/{occurrence_id}")
def update_occurrence_endpoint(
    occurrence_id: str,
    body: UpdateOccurrenceRequest,
    token: dict = Depends(_require_token),
) -> dict:
    occ = series_storage.get_occurrence(occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    rm = _get_room_or_404(occ.room_id)
    _require_role(rm, token["uid"], "organizer", "teacher")

    updates: dict = {}
    if body.location is not None:
        updates["location"] = body.location
    if body.host is not None:
        updates["host"] = body.host
    if body.enable_check_in is not None:
        updates["enable_check_in"] = body.enable_check_in

    if body.status == "cancelled":
        result = skip_occurrence(occurrence_id)
    elif body.status == "completed":
        result = complete_occurrence(occurrence_id)
    elif body.scheduled_for is not None:
        result = reschedule_occurrence(occurrence_id, body.scheduled_for)
    elif body.overrides is not None:
        result = edit_occurrence(occurrence_id, body.overrides.to_model())
    elif updates:
        result = series_storage.update_occurrence(occurrence_id, updates)
    else:
        raise HTTPException(status_code=400, detail="No valid update field provided")

    # Apply additional field updates alongside status/override changes
    if updates and (body.status or body.scheduled_for or body.overrides):
        result = series_storage.update_occurrence(occurrence_id, updates)

    return result.to_dict()


@router.delete("/occurrences/{occurrence_id}", status_code=204)
def delete_occurrence_endpoint(
    occurrence_id: str,
    token: dict = Depends(_require_token),
) -> None:
    occ = series_storage.get_occurrence(occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    rm = _get_room_or_404(occ.room_id)
    _require_organizer(rm, token["uid"])
    series_storage.delete_occurrence(occurrence_id)


@router.post("/series/{series_id}/occurrences/{occurrence_id}/regenerate-rotation", status_code=200)
def regenerate_rotation_from_occurrence_endpoint(
    series_id: str,
    occurrence_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    """Re-apply rotation to all subsequent occurrences, continuing from the target occurrence's host.

    Use case: User manually fixes one occurrence's host, then wants all following
    occurrences to continue the rotation pattern from that point.

    Example:
      - Rotation: [A, B, C]
      - User changes occurrence #3's host to "A"
      - Calling this endpoint re-assigns #4+ as B, C, A, B, C...

    Returns: {"updated_count": int, "starting_index": int, "message": str, "warnings": list}
    """
    s = _get_series_or_404(series_id)
    rm = _get_room_or_404(s.room_id)
    _require_role(rm, token["uid"], "organizer", "teacher")

    occ = series_storage.get_occurrence(occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    if occ.series_id != series_id:
        raise HTTPException(status_code=400, detail="Occurrence does not belong to this series")

    try:
        from occurrence_service import regenerate_rotation_from_occurrence
        result = regenerate_rotation_from_occurrence(series_id, occurrence_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# CheckIn endpoints
# ---------------------------------------------------------------------------

@router.post("/occurrences/{occurrence_id}/check-ins", status_code=201)
def upsert_check_in(
    occurrence_id: str,
    body: UpsertCheckInRequest,
    token: dict = Depends(_require_token),
) -> dict:
    """Create or update the calling user's check-in for an occurrence."""
    occ = series_storage.get_occurrence(occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    rm = _get_room_or_404(occ.room_id)
    _require_member(rm, token["uid"])

    uid = token["uid"]
    display_name = token.get("name") or token.get("email") or uid[:8]
    # Check if already exists
    existing = series_storage.get_check_in_for_user(occurrence_id, uid)
    now = datetime.now(timezone.utc)

    if existing is not None:
        check_in = existing
        check_in.status = body.status
        check_in.note = body.note
        check_in.display_name = display_name
        if body.status == "confirmed":
            check_in.checked_in_at = now
    else:
        check_in = CheckIn(
            check_in_id=str(uuid.uuid4()),
            occurrence_id=occurrence_id,
            series_id=occ.series_id,
            room_id=occ.room_id,
            user_id=uid,
            display_name=display_name,
            status=body.status,
            note=body.note,
            checked_in_at=now if body.status == "confirmed" else None,
        )

    series_storage.save_check_in(check_in)
    return check_in.to_dict()


@router.get("/occurrences/{occurrence_id}/check-ins")
def list_check_ins(
    occurrence_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    occ = series_storage.get_occurrence(occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    rm = _get_room_or_404(occ.room_id)
    _require_role(rm, token["uid"], "organizer", "teacher")
    check_ins = series_storage.list_check_ins_for_occurrence(occurrence_id)
    return {"occurrence_id": occurrence_id, "check_ins": [ci.to_dict() for ci in check_ins]}


@router.get("/occurrences/{occurrence_id}/my-check-in")
def get_my_check_in(
    occurrence_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    """Return the calling user's check-in for an occurrence, if present."""
    occ = series_storage.get_occurrence(occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    rm = _get_room_or_404(occ.room_id)
    uid = token["uid"]
    _require_member(rm, uid)
    check_in = series_storage.get_check_in_for_user(occurrence_id, uid)
    return {
        "occurrence_id": occurrence_id,
        "check_in": check_in.to_dict() if check_in is not None else None,
    }


@router.patch("/check-ins/{check_in_id}")
def update_check_in(
    check_in_id: str,
    body: UpsertCheckInRequest,
    token: dict = Depends(_require_token),
) -> dict:
    """Update an existing check-in (organizer override or user self-update)."""
    ci = series_storage.get_check_in(check_in_id)
    if ci is None:
        raise HTTPException(status_code=404, detail="CheckIn not found")
    rm = _get_room_or_404(ci.room_id)
    uid = token["uid"]
    # Allow: the check-in owner themselves, or an organizer/teacher
    if uid != ci.user_id:
        _require_role(rm, uid, "organizer", "teacher")

    ci.status = body.status
    ci.note = body.note
    if body.status == "confirmed" and ci.checked_in_at is None:
        ci.checked_in_at = datetime.now(timezone.utc)
    series_storage.save_check_in(ci)
    return ci.to_dict()


@router.delete("/check-ins/{check_in_id}", status_code=204)
def delete_check_in(
    check_in_id: str,
    token: dict = Depends(_require_token),
) -> None:
    """Delete a check-in. Only the owner or an organizer can delete."""
    ci = series_storage.get_check_in(check_in_id)
    if ci is None:
        raise HTTPException(status_code=404, detail="CheckIn not found")
    rm = _get_room_or_404(ci.room_id)
    uid = token["uid"]
    if uid != ci.user_id:
        _require_role(rm, uid, "organizer", "teacher")
    series_storage.delete_check_in(check_in_id)


# ---------------------------------------------------------------------------
# Notification rule endpoints
# ---------------------------------------------------------------------------

class CreateNotificationRuleRequest(BaseModel):
    channel: str  # email | in_app | telegram | calendar
    remind_before_minutes: int
    series_id: Optional[str] = None
    target_roles: list[str] = []
    enabled: bool = True


@router.get('/rooms/{room_id}/notification-rules')
def list_notification_rules(
    room_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_member(rm, token['uid'])
    import series_storage as _ss
    rules = _ss.list_notification_rules_for_room(room_id)
    return {'room_id': room_id, 'rules': [r.to_dict() for r in rules]}


@router.post('/rooms/{room_id}/notification-rules', status_code=201)
def create_notification_rule(
    room_id: str,
    body: CreateNotificationRuleRequest,
    token: dict = Depends(_require_token),
) -> dict:
    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token['uid'])
    from models import NotificationRule
    import series_storage as _ss
    rule = NotificationRule(
        rule_id=str(uuid.uuid4()),
        room_id=room_id,
        series_id=body.series_id,
        channel=body.channel,
        remind_before_minutes=body.remind_before_minutes,
        enabled=body.enabled,
        target_roles=body.target_roles,
    )
    _ss.save_notification_rule(rule)
    return rule.to_dict()


@router.delete('/notification-rules/{rule_id}', status_code=204)
def delete_notification_rule(
    rule_id: str,
    token: dict = Depends(_require_token),
) -> None:
    import series_storage as _ss
    from db import get_client
    rule = _ss.get_notification_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail='NotificationRule not found')
    rm = _get_room_or_404(rule.room_id)
    _require_organizer(rm, token['uid'])
    db = get_client()
    db.collection(_ss.NOTIFICATION_RULES_COLLECTION).document(rule_id).delete()


# ---------------------------------------------------------------------------
# ICS export endpoints
# ---------------------------------------------------------------------------

@router.get('/occurrences/{occurrence_id}/ics')
def get_occurrence_ics(
    occurrence_id: str,
    token: dict = Depends(_require_token),
) -> object:
    """Export a single occurrence as an ICS file."""
    from fastapi.responses import Response
    occ = series_storage.get_occurrence(occurrence_id)
    if occ is None:
        raise HTTPException(status_code=404, detail='Occurrence not found')
    rm = _get_room_or_404(occ.room_id)
    _require_member(rm, token['uid'])
    s = series_storage.get_series(occ.series_id)
    if s is None:
        raise HTTPException(status_code=404, detail='Series not found')
    try:
        from ics_export import occurrence_to_ics, calendar_to_bytes
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    cal = occurrence_to_ics(occ, s)
    ics_bytes = calendar_to_bytes(cal)
    filename = f'occurrence-{occurrence_id}.ics'
    return Response(
        content=ics_bytes,
        media_type='text/calendar',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@router.get('/series/{series_id}/ics')
def get_series_ics(
    series_id: str,
    include_cancelled: bool = False,
    token: dict = Depends(_require_token),
) -> object:
    """Export all occurrences of a series as an ICS calendar feed."""
    from fastapi.responses import Response
    s = _get_series_or_404(series_id)
    rm = _get_room_or_404(s.room_id)
    _require_member(rm, token['uid'])
    occs = series_storage.list_occurrences_for_series(series_id)
    try:
        from ics_export import series_to_ics, calendar_to_bytes
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    cal = series_to_ics(s, occs, include_cancelled=include_cancelled)
    ics_bytes = calendar_to_bytes(cal)
    filename = f'series-{series_id}.ics'
    return Response(
        content=ics_bytes,
        media_type='text/calendar',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


# ---------------------------------------------------------------------------
# Telegram bot management endpoints
# ---------------------------------------------------------------------------


def _bot_public_dict(config: TelegramBotConfig) -> dict:
    """Return bot config fields safe for API responses (no token or secret)."""
    return {
        "bot_id": config.bot_id,
        "bot_username": config.bot_username,
        "mode": config.mode,
        "active": config.active,
    }


@router.post("/rooms/{room_id}/telegram-bot", status_code=201)
async def register_telegram_bot(
    room_id: str,
    body: RegisterTelegramBotRequest,
    token: dict = Depends(_require_token),
) -> dict:
    """Register a Telegram bot for a room."""
    import os
    import httpx

    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token["uid"])

    # Check no bot already exists for this room
    existing = telegram_storage.get_bot_config_for_room(room_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="A bot is already configured for this room")

    if body.mode not in ("read_only", "read_write"):
        raise HTTPException(status_code=400, detail="mode must be 'read_only' or 'read_write'")

    # Validate token by calling Telegram getMe
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.telegram.org/bot{body.bot_token}/getMe")
    if resp.status_code != 200 or not resp.json().get("ok"):
        raise HTTPException(status_code=400, detail="Invalid bot token: Telegram getMe failed")
    me = resp.json()["result"]
    bot_id = str(me["id"])
    bot_username = me.get("username", "")

    # Generate webhook secret
    webhook_secret = str(uuid.uuid4())

    # Register webhook with Telegram
    webhook_base_url = os.environ.get("WEBHOOK_BASE_URL", "")
    if not webhook_base_url:
        raise HTTPException(status_code=503, detail="WEBHOOK_BASE_URL is not configured")
    webhook_url = f"{webhook_base_url}/v2/channels/telegram/webhook/{bot_id}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{body.bot_token}/setWebhook",
            json={"url": webhook_url, "secret_token": webhook_secret},
        )
    if resp.status_code != 200 or not resp.json().get("ok"):
        raise HTTPException(status_code=502, detail="Failed to register webhook with Telegram")

    # Save config
    config = TelegramBotConfig(
        bot_id=bot_id,
        room_id=room_id,
        bot_token=body.bot_token,
        bot_username=bot_username,
        webhook_secret=webhook_secret,
        mode=body.mode,
        created_by=token["uid"],
    )
    telegram_storage.save_bot_config(config)

    return _bot_public_dict(config)


@router.get("/rooms/{room_id}/telegram-bot")
def get_telegram_bot(
    room_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    """Get the Telegram bot config for a room (without token)."""
    rm = _get_room_or_404(room_id)
    _require_member(rm, token["uid"])
    config = telegram_storage.get_bot_config_for_room(room_id)
    if config is None:
        raise HTTPException(status_code=404, detail="No bot configured for this room")
    return _bot_public_dict(config)


@router.patch("/rooms/{room_id}/telegram-bot")
def update_telegram_bot(
    room_id: str,
    body: UpdateTelegramBotRequest,
    token: dict = Depends(_require_token),
) -> dict:
    """Update the Telegram bot mode for a room."""
    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token["uid"])
    config = telegram_storage.get_bot_config_for_room(room_id)
    if config is None:
        raise HTTPException(status_code=404, detail="No bot configured for this room")
    if body.mode not in ("read_only", "read_write"):
        raise HTTPException(status_code=400, detail="mode must be 'read_only' or 'read_write'")
    config.mode = body.mode
    telegram_storage.save_bot_config(config)
    return _bot_public_dict(config)


@router.delete("/rooms/{room_id}/telegram-bot", status_code=200)
async def delete_telegram_bot(
    room_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    """Delete a room's Telegram bot and unregister the webhook."""
    import httpx

    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token["uid"])
    config = telegram_storage.get_bot_config_for_room(room_id)
    if config is None:
        raise HTTPException(status_code=404, detail="No bot configured for this room")

    # Call Telegram deleteWebhook
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{config.bot_token}/deleteWebhook"
        )

    telegram_storage.delete_links_for_bot(config.bot_id)
    telegram_storage.delete_bot_config(config.bot_id)
    return {"deleted": True}


@router.post("/rooms/{room_id}/telegram-bot/link-code", status_code=201)
def generate_link_code(
    room_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    """Generate a one-time link code for connecting a Telegram user to an app user."""
    import secrets
    from datetime import timedelta

    rm = _get_room_or_404(room_id)
    _require_organizer(rm, token["uid"])

    # Verify bot exists for this room
    config = telegram_storage.get_bot_config_for_room(room_id)
    if config is None:
        raise HTTPException(status_code=404, detail="No bot configured for this room")

    # Generate 6-char alphanumeric code
    code = secrets.token_hex(3).upper()  # 6 hex chars
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    telegram_storage.save_link_code(code, room_id, token["uid"], expires_at)

    return {"code": code, "expires_in": 300}


# ---------------------------------------------------------------------------
# Per-bot Telegram webhook endpoint
# ---------------------------------------------------------------------------


def _extract_telegram_user(message: dict) -> tuple[str, str, str]:
    """Extract (telegram_user_id, display_name, chat_id) from a Telegram message."""
    from_user = message.get("from", {})
    telegram_user_id = str(from_user.get("id", ""))
    first_name = from_user.get("first_name", "")
    last_name = from_user.get("last_name", "")
    display_name = f"{first_name} {last_name}".strip() if last_name else first_name
    chat_id = str(message.get("chat", {}).get("id", ""))
    return telegram_user_id, display_name, chat_id


async def _send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    """Send a text message via the Telegram Bot API."""
    import httpx

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


@router.post("/channels/telegram/webhook/{bot_id}", status_code=200)
async def telegram_bot_webhook(
    bot_id: str,
    raw_update: dict,
    x_telegram_bot_api_secret_token: str = Header(None),
) -> dict:
    """Receive a Telegram Update for a specific bot.

    Validates the per-bot webhook secret. Handles /start, /link, and
    general messages with identity checking.
    """
    import logging

    config = telegram_storage.get_bot_config(bot_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    if not config.active:
        raise HTTPException(status_code=403, detail="Bot is deactivated")
    if not x_telegram_bot_api_secret_token or x_telegram_bot_api_secret_token != config.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    logger = logging.getLogger(__name__)

    # Handle callback queries (inline button presses)
    callback_query = raw_update.get("callback_query")
    if callback_query:
        from telegram_chat_handler import handle_telegram_callback

        cb_from = callback_query.get("from", {})
        cb_telegram_user_id = str(cb_from.get("id", ""))
        if not cb_telegram_user_id:
            return {"ok": True}
        cb_link = telegram_storage.get_link_by_telegram_user(cb_telegram_user_id)
        if cb_link is None:
            # Can't process callback from unlinked user
            return {"ok": True}
        await handle_telegram_callback(
            bot_config=config,
            telegram_user_id=cb_telegram_user_id,
            app_uid=cb_link.app_uid,
            callback_query=callback_query,
        )
        return {"ok": True}

    message = raw_update.get("message")
    if not message:
        return {"ok": True}

    telegram_user_id, display_name, chat_id = _extract_telegram_user(message)
    if not telegram_user_id or not chat_id:
        return {"ok": True}

    text = (message.get("text") or "").strip()

    # Handle /start command
    if text == "/start" or text.startswith("/start "):
        await _send_telegram_message(
            config.bot_token,
            chat_id,
            "Welcome! To link your account, go to Room Settings > AI Assistant "
            "in the app, generate a link code, then send /link <code> here.",
        )
        return {"ok": True}

    # Handle /link command
    if text.startswith("/link"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _send_telegram_message(
                config.bot_token,
                chat_id,
                "Usage: /link <code>",
            )
            return {"ok": True}
        code = parts[1].strip()
        result = telegram_storage.get_and_consume_link_code(code)
        if result is None:
            await _send_telegram_message(
                config.bot_token,
                chat_id,
                "Invalid or expired code. Please generate a new one from the app.",
            )
            return {"ok": True}
        # Save the link
        link = TelegramUserLink(
            telegram_user_id=telegram_user_id,
            app_uid=result["app_uid"],
            display_name=display_name,
        )
        telegram_storage.save_telegram_link(link)
        await _send_telegram_message(
            config.bot_token,
            chat_id,
            f"You're now linked as {display_name}. You can manage this room's schedule.",
        )
        return {"ok": True}

    # For all other messages, check if user is linked
    existing_link = telegram_storage.get_link_by_telegram_user(telegram_user_id)
    if existing_link is None:
        await _send_telegram_message(
            config.bot_token,
            chat_id,
            "Please link your account first. Generate a link code in "
            "Room Settings > AI Assistant, then send /link <code> here.",
        )
        return {"ok": True}

    # Linked user — route through the assistant chat handler
    from telegram_chat_handler import handle_telegram_message

    await handle_telegram_message(
        bot_config=config,
        telegram_user_id=telegram_user_id,
        app_uid=existing_link.app_uid,
        chat_id=chat_id,
        text=text,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Channel / Telegram webhook endpoint (legacy global)
# ---------------------------------------------------------------------------

@router.post("/channels/telegram/webhook", status_code=200)
def telegram_webhook(raw_update: dict, x_telegram_bot_api_secret_token: str = Header(None)) -> dict:
    """Receive a Telegram Update, dispatch it through the TelegramAdapter.

    Telegram calls this URL when a new message arrives (webhook mode).
    The endpoint does not require a Firebase auth token because Telegram
    does not send one -- security is provided by a secret token header.

    Returns {"ok": true} to tell Telegram the update was accepted.
    """
    import os
    # Validate secret token if configured
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if webhook_secret:
        if not x_telegram_bot_api_secret_token or x_telegram_bot_api_secret_token != webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        from channels.telegram import TelegramAdapter
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise HTTPException(
            status_code=503,
            detail="TELEGRAM_BOT_TOKEN is not configured on the server.",
        )
    try:
        adapter = TelegramAdapter(token=token)
        adapter.dispatch(raw_update)
    except Exception as exc:
        # Log but return 200 so Telegram does not keep retrying
        import logging
        logging.getLogger(__name__).exception("Telegram dispatch error: %s", exc)

    return {"ok": True}


# Assistant endpoints
# ---------------------------------------------------------------------------

class AssistantMessageRequest(BaseModel):
    message: str
    room_context: dict | None = None
    history: list[dict] | None = None


@router.post('/rooms/{room_id}/assistant')
def assistant_chat(
    room_id: str,
    body: AssistantMessageRequest,
    token: dict = Depends(_require_token),
) -> object:
    import json as _json
    from fastapi.responses import StreamingResponse

    rm = _get_room_or_404(room_id)
    _require_role(rm, token['uid'], 'organizer', 'teacher')
    uid = token['uid']

    def _event_stream():
        for event in run_assistant_stream(
            message=body.message,
            room_id=room_id,
            uid=uid,
            room_context=body.room_context,
            history=body.history,
        ):
            yield f"data: {_json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_event_stream(), media_type='text/event-stream')


@router.post('/assistant/actions/{action_id}/confirm')
def confirm_action(
    action_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    pending = get_pending_action(action_id)
    if pending is None:
        raise HTTPException(status_code=404, detail='Action not found or expired')
    if pending.requested_by_uid != token['uid']:
        raise HTTPException(status_code=403, detail='Not your action')
    if pending.status != 'pending':
        raise HTTPException(status_code=409, detail=f'Action is already {pending.status}')

    rm = _get_room_or_404(pending.room_id)
    _require_role(rm, token['uid'], 'organizer', 'teacher')

    update_pending_action_status(action_id, 'confirmed')
    try:
        result = execute_action(pending)
        update_pending_action_status(action_id, 'executed', result=result)
        return {'status': 'executed', 'action_id': action_id, 'result': result}
    except Exception as exc:
        update_pending_action_status(action_id, 'failed', error=str(exc))
        raise HTTPException(status_code=500, detail=f'Action execution failed: {exc}') from exc


@router.post('/assistant/actions/{action_id}/cancel', status_code=200)
def cancel_action(
    action_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    pending = get_pending_action(action_id)
    if pending is None:
        raise HTTPException(status_code=404, detail='Action not found or expired')
    if pending.requested_by_uid != token['uid']:
        raise HTTPException(status_code=403, detail='Not your action')
    if pending.status != 'pending':
        raise HTTPException(status_code=409, detail=f'Action is already {pending.status}')

    update_pending_action_status(action_id, 'cancelled')
    return {'status': 'cancelled', 'action_id': action_id}
