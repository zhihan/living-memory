"""Firestore-backed storage for Workspaces and workspace membership."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from firestore_storage import _get_client
from models import MemberRole, Workspace

WORKSPACES_COLLECTION = "workspaces"
WORKSPACE_INVITES_SUBCOLLECTION = "workspace_invites"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_workspace(workspace: Workspace) -> Workspace:
    """Persist a new Workspace document. workspace_id is used as doc ID."""
    if not workspace.owner_uids:
        raise ValueError("Workspace must have at least one owner")
    db = _get_client()
    ref = db.collection(WORKSPACES_COLLECTION).document(workspace.workspace_id)
    if ref.get().exists:
        raise ValueError(f"Workspace already exists: {workspace.workspace_id}")
    now = _utcnow()
    workspace.created_at = now
    workspace.updated_at = now
    for uid in workspace.owner_uids:
        workspace.member_roles.setdefault(uid, "organizer")
    ref.set(workspace.to_dict())
    return workspace


def get_workspace(workspace_id: str) -> Workspace | None:
    """Fetch a Workspace by its ID. Returns None if not found."""
    db = _get_client()
    doc = db.collection(WORKSPACES_COLLECTION).document(workspace_id).get()
    if not doc.exists:
        return None
    return Workspace.from_dict(doc.to_dict())


def update_workspace(workspace_id: str, updates: dict) -> Workspace:
    """Apply a partial update to a Workspace. Raises if not found."""
    db = _get_client()
    ref = db.collection(WORKSPACES_COLLECTION).document(workspace_id)
    doc = ref.get()
    if not doc.exists:
        raise ValueError(f"Workspace not found: {workspace_id}")
    updates["updated_at"] = _utcnow()
    ref.update(updates)
    return Workspace.from_dict({**doc.to_dict(), **updates})


def delete_workspace(workspace_id: str) -> None:
    """Hard-delete a Workspace document. Does not cascade to sub-collections."""
    db = _get_client()
    db.collection(WORKSPACES_COLLECTION).document(workspace_id).delete()


def list_workspaces_for_user(uid: str) -> list[Workspace]:
    """Return all Workspaces where uid is listed as an owner."""
    db = _get_client()
    docs = (
        db.collection(WORKSPACES_COLLECTION)
        .where("owner_uids", "array_contains", uid)
        .stream()
    )
    return [Workspace.from_dict(doc.to_dict()) for doc in docs]


def add_member(workspace_id: str, uid: str, role: MemberRole) -> Workspace:
    """Add or update uid role in workspace_id."""
    from google.cloud.firestore import ArrayUnion
    db = _get_client()
    ref = db.collection(WORKSPACES_COLLECTION).document(workspace_id)
    if not ref.get().exists:
        raise ValueError(f"Workspace not found: {workspace_id}")
    updates: dict = {
        f"member_roles.{uid}": role,
        "updated_at": _utcnow(),
    }
    if role == "organizer":
        updates["owner_uids"] = ArrayUnion([uid])
    ref.update(updates)
    return get_workspace(workspace_id)  # type: ignore[return-value]


def remove_member(workspace_id: str, uid: str) -> Workspace:
    """Remove uid from workspace_id. Raises if would leave no organizers."""
    from google.cloud.firestore import ArrayRemove
    from google.cloud.firestore_v1 import DELETE_FIELD
    workspace = get_workspace(workspace_id)
    if workspace is None:
        raise ValueError(f"Workspace not found: {workspace_id}")
    current_role = workspace.member_roles.get(uid)
    if current_role is None:
        raise ValueError(f"User {uid!r} is not a member of {workspace_id!r}")
    if current_role == "organizer":
        organizer_count = sum(1 for r in workspace.member_roles.values() if r == "organizer")
        if organizer_count <= 1:
            raise ValueError("Cannot remove the last organizer of a workspace")
    db = _get_client()
    ref = db.collection(WORKSPACES_COLLECTION).document(workspace_id)
    updates: dict = {
        f"member_roles.{uid}": DELETE_FIELD,
        "updated_at": _utcnow(),
    }
    if current_role == "organizer":
        updates["owner_uids"] = ArrayRemove([uid])
    ref.update(updates)
    return get_workspace(workspace_id)  # type: ignore[return-value]


def get_member_role(workspace_id: str, uid: str) -> MemberRole | None:
    """Return uid role in workspace_id, or None if not a member."""
    workspace = get_workspace(workspace_id)
    if workspace is None:
        return None
    return workspace.member_roles.get(uid)  # type: ignore[return-value]


def create_workspace_invite(
    workspace_id: str,
    created_by: str,
    role: MemberRole = "participant",
    expires_in_days: int = 7,
) -> dict:
    """Generate a shareable invite for a workspace."""
    valid_roles = ("organizer", "participant", "teacher", "assistant", "student")
    if role not in valid_roles:
        raise ValueError(f"Invalid role: {role!r}")
    invite_id = secrets.token_urlsafe(16)
    now = _utcnow()
    invite_doc = {
        "invite_id": invite_id,
        "workspace_id": workspace_id,
        "created_by": created_by,
        "created_at": now,
        "expires_at": now + timedelta(days=expires_in_days),
        "accepted_by": None,
        "role": role,
    }
    db = _get_client()
    (db.collection(WORKSPACES_COLLECTION)
     .document(workspace_id)
     .collection(WORKSPACE_INVITES_SUBCOLLECTION)
     .document(invite_id)
     .set(invite_doc))
    return invite_doc


def find_workspace_invite(invite_id: str) -> dict | None:
    """Find a workspace invite by ID (collection group query)."""
    db = _get_client()
    docs = (
        db.collection_group(WORKSPACE_INVITES_SUBCOLLECTION)
        .where("invite_id", "==", invite_id)
        .limit(1)
        .stream()
    )
    for doc in docs:
        return doc.to_dict()
    return None


def accept_workspace_invite(invite_id: str, accepting_uid: str) -> dict:
    """Accept a workspace invite: add user and mark invite consumed."""
    invite = find_workspace_invite(invite_id)
    if invite is None:
        raise ValueError("Invite not found")
    if invite.get("accepted_by") is not None:
        raise ValueError("Invite has already been accepted")
    now = _utcnow()
    expires_at = invite.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            raise ValueError("Invite has expired")
    workspace_id = invite["workspace_id"]
    role: MemberRole = invite.get("role", "participant")
    add_member(workspace_id, accepting_uid, role)
    db = _get_client()
    (db.collection(WORKSPACES_COLLECTION)
     .document(workspace_id)
     .collection(WORKSPACE_INVITES_SUBCOLLECTION)
     .document(invite_id)
     .update({"accepted_by": accepting_uid}))
    invite["accepted_by"] = accepting_uid
    return invite
