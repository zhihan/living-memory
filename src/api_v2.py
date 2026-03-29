"""API v2 — Workspaces, Series, Occurrences, and CheckIns.

Mounted at /v2 on the main FastAPI app.  All routes enforce role-based
permissions using the same Firebase Auth token verification as the v1 API.

Route overview:
  POST   /v2/workspaces
  GET    /v2/workspaces/{workspace_id}
  PATCH  /v2/workspaces/{workspace_id}
  DELETE /v2/workspaces/{workspace_id}
  GET    /v2/workspaces/{workspace_id}/members
  POST   /v2/workspaces/{workspace_id}/members
  DELETE /v2/workspaces/{workspace_id}/members/{uid}
  POST   /v2/workspaces/{workspace_id}/invites
  POST   /v2/invites/{invite_id}/accept

  POST   /v2/workspaces/{workspace_id}/series
  GET    /v2/workspaces/{workspace_id}/series
  GET    /v2/series/{series_id}
  PATCH  /v2/series/{series_id}
  DELETE /v2/series/{series_id}

  GET    /v2/workspaces/{workspace_id}/occurrences
  GET    /v2/series/{series_id}/occurrences
  POST   /v2/series/{series_id}/occurrences/generate
  GET    /v2/occurrences/{occurrence_id}
  PATCH  /v2/occurrences/{occurrence_id}

  POST   /v2/occurrences/{occurrence_id}/check-ins
  GET    /v2/occurrences/{occurrence_id}/check-ins
  PATCH  /v2/check-ins/{check_in_id}
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, field_validator

import series_storage
import workspace_storage
from models import (
    CheckIn,
    MemberRole,
    Occurrence,
    OccurrenceOverrides,
    ScheduleRule,
    Series,
    Workspace,
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


def _get_workspace_or_404(workspace_id: str) -> Workspace:
    ws = workspace_storage.get_workspace(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    return ws


def _get_series_or_404(series_id: str) -> Series:
    s = series_storage.get_series(series_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Series not found: {series_id}")
    return s


def _require_role(workspace: Workspace, uid: str, *roles: MemberRole) -> None:
    """Raise 403 unless uid holds one of the required roles in workspace."""
    actual_role = workspace.member_roles.get(uid)
    if actual_role not in roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role required: {roles}. You have: {actual_role!r}",
        )


def _require_organizer(workspace: Workspace, uid: str) -> None:
    _require_role(workspace, uid, "organizer")


def _require_member(workspace: Workspace, uid: str) -> None:
    """Any workspace member (any role) may access this resource."""
    if uid not in workspace.member_roles and uid not in workspace.owner_uids:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class ScheduleRuleIn(BaseModel):
    frequency: str
    weekdays: list[int] = []
    interval: int = 1
    until: Optional[str] = None
    count: Optional[int] = None

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


class CreateWorkspaceRequest(BaseModel):
    title: str
    type: str = "shared"
    timezone: str = "UTC"
    description: Optional[str] = None


class UpdateWorkspaceRequest(BaseModel):
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
    description: Optional[str] = None


class UpdateSeriesRequest(BaseModel):
    title: Optional[str] = None
    default_time: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    default_location: Optional[str] = None
    default_online_link: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    schedule_rule: Optional[ScheduleRuleIn] = None


class GenerateOccurrencesRequest(BaseModel):
    start_date: str  # ISO date "YYYY-MM-DD"
    end_date: str    # ISO date "YYYY-MM-DD"
    workspace_timezone: Optional[str] = None  # overrides workspace default


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
    overrides: Optional[OccurrenceOverridesIn] = None


class UpsertCheckInRequest(BaseModel):
    status: str  # "confirmed", "declined", "missed"
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Workspace endpoints
# ---------------------------------------------------------------------------

@router.post("/workspaces", status_code=201)
def create_workspace(
    body: CreateWorkspaceRequest,
    token: dict = Depends(_require_token),
) -> dict:
    """Create a new workspace. The caller becomes the first organizer."""
    uid = token["uid"]
    ws = Workspace(
        workspace_id=str(uuid.uuid4()),
        title=body.title,
        type=body.type,
        timezone=body.timezone,
        owner_uids=[uid],
        member_roles={uid: "organizer"},
        description=body.description,
    )
    try:
        workspace_storage.create_workspace(ws)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ws.to_dict()


@router.get("/workspaces")
def list_workspaces(
    token: dict = Depends(_require_token),
) -> dict:
    """Return all workspaces where the caller is an owner."""
    uid = token["uid"]
    workspaces = workspace_storage.list_workspaces_for_user(uid)
    return {"workspaces": [ws.to_dict() for ws in workspaces]}


@router.get("/workspaces/{workspace_id}")
def get_workspace(
    workspace_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    uid = token["uid"]
    _require_member(ws, uid)
    return ws.to_dict()


@router.patch("/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_organizer(ws, token["uid"])
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = workspace_storage.update_workspace(workspace_id, updates)
    return updated.to_dict()


@router.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(
    workspace_id: str,
    token: dict = Depends(_require_token),
) -> None:
    ws = _get_workspace_or_404(workspace_id)
    _require_organizer(ws, token["uid"])
    workspace_storage.delete_workspace(workspace_id)


@router.get("/workspaces/{workspace_id}/members")
def list_members(
    workspace_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_member(ws, token["uid"])
    return {"workspace_id": workspace_id, "members": ws.member_roles}


@router.post("/workspaces/{workspace_id}/members", status_code=201)
def add_member(
    workspace_id: str,
    body: AddMemberRequest,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_organizer(ws, token["uid"])
    updated = workspace_storage.add_member(workspace_id, body.uid, body.role)
    return {"workspace_id": workspace_id, "uid": body.uid, "role": body.role}


@router.delete("/workspaces/{workspace_id}/members/{uid}", status_code=204)
def remove_member(
    workspace_id: str,
    uid: str,
    token: dict = Depends(_require_token),
) -> None:
    ws = _get_workspace_or_404(workspace_id)
    _require_organizer(ws, token["uid"])
    try:
        workspace_storage.remove_member(workspace_id, uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Invite endpoints
# ---------------------------------------------------------------------------

@router.post("/workspaces/{workspace_id}/invites", status_code=201)
def create_invite(
    workspace_id: str,
    body: CreateInviteRequest,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_organizer(ws, token["uid"])
    try:
        invite = workspace_storage.create_workspace_invite(
            workspace_id,
            created_by=token["uid"],
            role=body.role,
            expires_in_days=body.expires_in_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Omit the datetime objects for clean JSON (convert to iso strings)
    return {
        "invite_id": invite["invite_id"],
        "workspace_id": invite["workspace_id"],
        "role": invite["role"],
        "created_by": invite["created_by"],
        "expires_at": invite["expires_at"].isoformat(),
    }


@router.post("/v2/invites/{invite_id}/accept", status_code=200)
def accept_invite(
    invite_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    uid = token["uid"]
    try:
        invite = workspace_storage.accept_workspace_invite(invite_id, uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"accepted": True, "workspace_id": invite["workspace_id"], "role": invite["role"]}


# ---------------------------------------------------------------------------
# Series endpoints
# ---------------------------------------------------------------------------

@router.post("/workspaces/{workspace_id}/series", status_code=201)
def create_series(
    workspace_id: str,
    body: CreateSeriesRequest,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_role(ws, token["uid"], "organizer", "teacher")
    series = Series(
        series_id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        kind=body.kind,
        title=body.title,
        schedule_rule=body.schedule_rule.to_model(),
        default_time=body.default_time,
        default_duration_minutes=body.default_duration_minutes,
        default_location=body.default_location,
        default_online_link=body.default_online_link,
        description=body.description,
        created_by=token["uid"],
    )
    series_storage.create_series(series)
    return series.to_dict()


@router.get("/workspaces/{workspace_id}/series")
def list_series(
    workspace_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_member(ws, token["uid"])
    all_series = series_storage.list_series_for_workspace(workspace_id)
    return {"workspace_id": workspace_id, "series": [s.to_dict() for s in all_series]}


@router.get("/series/{series_id}")
def get_series(
    series_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    s = _get_series_or_404(series_id)
    ws = _get_workspace_or_404(s.workspace_id)
    _require_member(ws, token["uid"])
    return s.to_dict()


@router.patch("/series/{series_id}")
def update_series(
    series_id: str,
    body: UpdateSeriesRequest,
    token: dict = Depends(_require_token),
) -> dict:
    s = _get_series_or_404(series_id)
    ws = _get_workspace_or_404(s.workspace_id)
    _require_role(ws, token["uid"], "organizer", "teacher")
    updates: dict = {}
    for field in ("title", "default_time", "default_duration_minutes",
                  "default_location", "default_online_link", "status", "description"):
        val = getattr(body, field)
        if val is not None:
            updates[field] = val
    if body.schedule_rule is not None:
        updates["schedule_rule"] = body.schedule_rule.to_model().to_dict()
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updated = series_storage.update_series(series_id, updates)
    return updated.to_dict()


@router.delete("/series/{series_id}", status_code=204)
def delete_series(
    series_id: str,
    token: dict = Depends(_require_token),
) -> None:
    s = _get_series_or_404(series_id)
    ws = _get_workspace_or_404(s.workspace_id)
    _require_organizer(ws, token["uid"])
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
    ws = _get_workspace_or_404(s.workspace_id)
    _require_role(ws, token["uid"], "organizer", "teacher")
    try:
        start = date.fromisoformat(body.start_date)
        end = date.fromisoformat(body.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {exc}") from exc
    tz = body.workspace_timezone or ws.timezone
    new_occs = generate_and_save(s, tz, start, end)
    return {"created": len(new_occs), "occurrences": [o.to_dict() for o in new_occs]}


@router.get("/workspaces/{workspace_id}/occurrences")
def list_workspace_occurrences(
    workspace_id: str,
    status: Optional[str] = None,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_member(ws, token["uid"])
    occs = series_storage.list_occurrences_for_workspace(workspace_id, status=status)
    return {"workspace_id": workspace_id, "occurrences": [o.to_dict() for o in occs]}


@router.get("/series/{series_id}/occurrences")
def list_series_occurrences(
    series_id: str,
    status: Optional[str] = None,
    token: dict = Depends(_require_token),
) -> dict:
    s = _get_series_or_404(series_id)
    ws = _get_workspace_or_404(s.workspace_id)
    _require_member(ws, token["uid"])
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
    ws = _get_workspace_or_404(occ.workspace_id)
    _require_member(ws, token["uid"])
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
    ws = _get_workspace_or_404(occ.workspace_id)
    _require_role(ws, token["uid"], "organizer", "teacher")

    if body.status == "cancelled":
        result = skip_occurrence(occurrence_id)
    elif body.status == "completed":
        result = complete_occurrence(occurrence_id)
    elif body.scheduled_for is not None:
        result = reschedule_occurrence(occurrence_id, body.scheduled_for)
    elif body.overrides is not None:
        result = edit_occurrence(occurrence_id, body.overrides.to_model())
    else:
        raise HTTPException(status_code=400, detail="No valid update field provided")
    return result.to_dict()


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
    ws = _get_workspace_or_404(occ.workspace_id)
    _require_member(ws, token["uid"])

    uid = token["uid"]
    # Check if already exists
    existing = series_storage.get_check_in_for_user(occurrence_id, uid)
    now = datetime.now(timezone.utc)

    if existing is not None:
        check_in = existing
        check_in.status = body.status
        check_in.note = body.note
        if body.status == "confirmed":
            check_in.checked_in_at = now
    else:
        check_in = CheckIn(
            check_in_id=str(uuid.uuid4()),
            occurrence_id=occurrence_id,
            series_id=occ.series_id,
            workspace_id=occ.workspace_id,
            user_id=uid,
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
    ws = _get_workspace_or_404(occ.workspace_id)
    _require_member(ws, token["uid"])
    check_ins = series_storage.list_check_ins_for_occurrence(occurrence_id)
    return {"occurrence_id": occurrence_id, "check_ins": [ci.to_dict() for ci in check_ins]}


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
    ws = _get_workspace_or_404(ci.workspace_id)
    uid = token["uid"]
    # Allow: the check-in owner themselves, or an organizer/teacher
    if uid != ci.user_id:
        _require_role(ws, uid, "organizer", "teacher")

    ci.status = body.status
    ci.note = body.note
    if body.status == "confirmed" and ci.checked_in_at is None:
        ci.checked_in_at = datetime.now(timezone.utc)
    series_storage.save_check_in(ci)
    return ci.to_dict()


# ---------------------------------------------------------------------------
# Notification rule endpoints
# ---------------------------------------------------------------------------

class CreateNotificationRuleRequest(BaseModel):
    channel: str  # email | in_app | telegram | calendar
    remind_before_minutes: int
    series_id: Optional[str] = None
    target_roles: list[str] = []
    enabled: bool = True


@router.get('/workspaces/{workspace_id}/notification-rules')
def list_notification_rules(
    workspace_id: str,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_member(ws, token['uid'])
    import series_storage as _ss
    rules = _ss.list_notification_rules_for_workspace(workspace_id)
    return {'workspace_id': workspace_id, 'rules': [r.to_dict() for r in rules]}


@router.post('/workspaces/{workspace_id}/notification-rules', status_code=201)
def create_notification_rule(
    workspace_id: str,
    body: CreateNotificationRuleRequest,
    token: dict = Depends(_require_token),
) -> dict:
    ws = _get_workspace_or_404(workspace_id)
    _require_organizer(ws, token['uid'])
    from models import NotificationRule
    import series_storage as _ss
    rule = NotificationRule(
        rule_id=str(uuid.uuid4()),
        workspace_id=workspace_id,
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
    from firestore_storage import _get_client
    rule = _ss.get_notification_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail='NotificationRule not found')
    ws = _get_workspace_or_404(rule.workspace_id)
    _require_organizer(ws, token['uid'])
    db = _get_client()
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
    ws = _get_workspace_or_404(occ.workspace_id)
    _require_member(ws, token['uid'])
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
    ws = _get_workspace_or_404(s.workspace_id)
    _require_member(ws, token['uid'])
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
