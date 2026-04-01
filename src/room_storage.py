"""Firestore-backed storage for Rooms and room membership."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from db import get_client as _get_client
from models import MemberRole, Room

ROOMS_COLLECTION = "workspaces"
ROOM_INVITES_SUBCOLLECTION = "workspace_invites"
ROOM_INVITE_LOOKUP_COLLECTION = "workspace_invite_lookup"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_email(email: str | None) -> None:
    """Validate email format using a simple regex. Raises ValueError if invalid."""
    if email is None:
        return
    # Simple email regex: at least one char, @, at least one char, dot, at least one char
    pattern = r'^[^@]+@[^@]+\.[^@]+$'
    if not re.match(pattern, email):
        raise ValueError(f"Invalid email format: {email}")


def create_room(room: Room) -> Room:
    """Persist a new Room document. room_id is used as doc ID."""
    if not room.owner_uids:
        raise ValueError("Room must have at least one owner")
    db = _get_client()
    ref = db.collection(ROOMS_COLLECTION).document(room.room_id)
    if ref.get().exists:
        raise ValueError(f"Room already exists: {room.room_id}")
    now = _utcnow()
    room.created_at = now
    room.updated_at = now
    for uid in room.owner_uids:
        room.member_roles.setdefault(uid, "organizer")
    ref.set(room.to_dict())
    return room


def get_room(room_id: str) -> Room | None:
    """Fetch a Room by its ID. Returns None if not found."""
    db = _get_client()
    doc = db.collection(ROOMS_COLLECTION).document(room_id).get()
    if not doc.exists:
        return None
    return Room.from_dict(doc.to_dict())


def update_room(room_id: str, updates: dict) -> Room:
    """Apply a partial update to a Room. Raises if not found."""
    db = _get_client()
    ref = db.collection(ROOMS_COLLECTION).document(room_id)
    doc = ref.get()
    if not doc.exists:
        raise ValueError(f"Room not found: {room_id}")
    updates["updated_at"] = _utcnow()
    ref.update(updates)
    return Room.from_dict({**doc.to_dict(), **updates})


def delete_room(room_id: str) -> None:
    """Hard-delete a Room document. Does not cascade to sub-collections."""
    db = _get_client()
    db.collection(ROOMS_COLLECTION).document(room_id).delete()


def list_rooms_for_user(uid: str) -> list[Room]:
    """Return all Rooms where uid is listed as an owner."""
    db = _get_client()
    docs = (
        db.collection(ROOMS_COLLECTION)
        .where("owner_uids", "array_contains", uid)
        .stream()
    )
    return [Room.from_dict(doc.to_dict()) for doc in docs]


def add_member(room_id: str, uid: str, role: MemberRole) -> Room:
    """Add or update uid role in room_id."""
    db = _get_client()
    ref = db.collection(ROOMS_COLLECTION).document(room_id)
    if not ref.get().exists:
        raise ValueError(f"Room not found: {room_id}")
    updates: dict = {
        f"member_roles.{uid}": role,
        "updated_at": _utcnow(),
    }
    if role == "organizer":
        from google.cloud.firestore_v1 import ArrayUnion
        updates["owner_uids"] = ArrayUnion([uid])
    ref.update(updates)
    return get_room(room_id)  # type: ignore[return-value]


def update_member_profile(
    room_id: str,
    uid: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
) -> Room:
    """Persist lightweight display metadata for a room member."""
    _validate_email(email)
    db = _get_client()
    ref = db.collection(ROOMS_COLLECTION).document(room_id)
    if not ref.get().exists:
        raise ValueError(f"Room not found: {room_id}")
    updates = {
        f"member_profiles.{uid}": {
            "display_name": display_name,
            "email": email,
        },
        "updated_at": _utcnow(),
    }
    ref.update(updates)
    return get_room(room_id)  # type: ignore[return-value]


def remove_member(room_id: str, uid: str) -> Room:
    """Remove uid from room_id. Raises if would leave no organizers."""
    room = get_room(room_id)
    if room is None:
        raise ValueError(f"Room not found: {room_id}")
    current_role = room.member_roles.get(uid)
    if current_role is None:
        raise ValueError(f"User {uid!r} is not a member of {room_id!r}")
    if current_role == "organizer":
        organizer_count = sum(1 for r in room.member_roles.values() if r == "organizer")
        if organizer_count <= 1:
            raise ValueError("Cannot remove the last organizer of a room")
    db = _get_client()
    ref = db.collection(ROOMS_COLLECTION).document(room_id)
    from google.cloud.firestore_v1 import DELETE_FIELD
    updates: dict = {
        f"member_roles.{uid}": DELETE_FIELD,
        f"member_profiles.{uid}": DELETE_FIELD,
        "updated_at": _utcnow(),
    }
    if current_role == "organizer":
        from google.cloud.firestore_v1 import ArrayRemove
        updates["owner_uids"] = ArrayRemove([uid])
    ref.update(updates)
    return get_room(room_id)  # type: ignore[return-value]


def get_member_role(room_id: str, uid: str) -> MemberRole | None:
    """Return uid role in room_id, or None if not a member."""
    room = get_room(room_id)
    if room is None:
        return None
    return room.member_roles.get(uid)  # type: ignore[return-value]


def create_room_invite(
    room_id: str,
    created_by: str,
    role: MemberRole = "participant",
    expires_in_days: int = 7,
) -> dict:
    """Generate a shareable invite for a room."""
    valid_roles = ("organizer", "participant", "teacher", "assistant", "student")
    if role not in valid_roles:
        raise ValueError(f"Invalid role: {role!r}")
    invite_id = secrets.token_urlsafe(16)
    now = _utcnow()
    invite_doc = {
        "invite_id": invite_id,
        "room_id": room_id,
        "created_by": created_by,
        "created_at": now,
        "expires_at": now + timedelta(days=expires_in_days),
        "accepted_by": None,
        "role": role,
    }
    db = _get_client()
    (db.collection(ROOMS_COLLECTION)
     .document(room_id)
     .collection(ROOM_INVITES_SUBCOLLECTION)
     .document(invite_id)
     .set(invite_doc))
    (db.collection(ROOM_INVITE_LOOKUP_COLLECTION)
     .document(invite_id)
     .set(invite_doc))
    return invite_doc


def find_room_invite(invite_id: str) -> dict | None:
    """Find a room invite by ID without relying on collection-group indexes."""
    db = _get_client()

    # Preferred path for newly-created invites.
    lookup_doc = db.collection(ROOM_INVITE_LOOKUP_COLLECTION).document(invite_id).get()
    if lookup_doc.exists:
        return lookup_doc.to_dict()

    # Backward-compatible path for older invites created before the lookup
    # collection existed. Since invite_id is also the subcollection document id,
    # we can probe each room directly without requiring a Firestore index.
    room_docs = db.collection(ROOMS_COLLECTION).stream()
    for room_doc in room_docs:
        rid = room_doc.id
        invite_doc = (
            db.collection(ROOMS_COLLECTION)
            .document(rid)
            .collection(ROOM_INVITES_SUBCOLLECTION)
            .document(invite_id)
            .get()
        )
        if invite_doc.exists:
            return invite_doc.to_dict()
    return None


def accept_room_invite(invite_id: str, accepting_uid: str) -> dict:
    """Accept a room invite: add user and mark invite consumed."""
    invite = find_room_invite(invite_id)
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
    room_id = invite.get("room_id") or invite.get("workspace_id")
    role: MemberRole = invite.get("role", "participant")
    add_member(room_id, accepting_uid, role)
    db = _get_client()
    (db.collection(ROOMS_COLLECTION)
     .document(room_id)
     .collection(ROOM_INVITES_SUBCOLLECTION)
     .document(invite_id)
     .update({"accepted_by": accepting_uid}))
    (db.collection(ROOM_INVITE_LOOKUP_COLLECTION)
     .document(invite_id)
     .set({"accepted_by": accepting_uid}, merge=True))
    invite["accepted_by"] = accepting_uid
    return invite
