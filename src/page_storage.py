"""Firestore-backed storage for pages, invites, and audit logs."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

PAGES_COLLECTION = "pages"
INVITES_SUBCOLLECTION = "invites"
AUDIT_LOG_COLLECTION = "audit_log"
USERS_COLLECTION = "users"


from firestore_storage import _get_client


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Page:
    slug: str
    title: str
    visibility: str  # "public" or "personal"
    owner_uids: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None
    description: str | None = None
    delete_after: datetime | None = None
    timezone: str | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "title": self.title,
            "description": self.description,
            "visibility": self.visibility,
            "owner_uids": self.owner_uids,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
            "delete_after": self.delete_after,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, slug: str, data: dict) -> Page:
        return cls(
            slug=slug,
            title=data["title"],
            description=data.get("description"),
            visibility=data["visibility"],
            owner_uids=list(data.get("owner_uids", [])),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            delete_after=data.get("delete_after"),
            timezone=data.get("timezone"),
        )


@dataclass
class Invite:
    invite_id: str
    page_slug: str
    created_by: str
    created_at: datetime | None = None
    expires_at: datetime | None = None
    accepted_by: str | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "invite_id": self.invite_id,
            "created_by": self.created_by,
            "created_at": self.created_at or now,
            "expires_at": self.expires_at or (now + timedelta(days=7)),
            "accepted_by": self.accepted_by,
        }

    @classmethod
    def from_dict(cls, page_slug: str, data: dict) -> Invite:
        return cls(
            invite_id=data["invite_id"],
            page_slug=page_slug,
            created_by=data["created_by"],
            created_at=data.get("created_at"),
            expires_at=data.get("expires_at"),
            accepted_by=data.get("accepted_by"),
        )


@dataclass
class AuditLogEntry:
    entry_id: str
    page_slug: str
    action: str
    actor_uid: str
    target_uid: str | None = None
    metadata: dict | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "page_slug": self.page_slug,
            "action": self.action,
            "actor_uid": self.actor_uid,
            "target_uid": self.target_uid,
            "metadata": self.metadata,
            "created_at": self.created_at or _utcnow(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> AuditLogEntry:
        return cls(
            entry_id=data["entry_id"],
            page_slug=data["page_slug"],
            action=data["action"],
            actor_uid=data["actor_uid"],
            target_uid=data.get("target_uid"),
            metadata=data.get("metadata"),
            created_at=data.get("created_at"),
        )


@dataclass
class User:
    uid: str
    created_at: datetime | None = None
    display_name: str | None = None
    photo_url: str | None = None
    default_personal_page_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "created_at": self.created_at or _utcnow(),
            "display_name": self.display_name,
            "photo_url": self.photo_url,
            "default_personal_page_id": self.default_personal_page_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> User:
        return cls(
            uid=data["uid"],
            created_at=data.get("created_at"),
            display_name=data.get("display_name"),
            photo_url=data.get("photo_url"),
            default_personal_page_id=data.get("default_personal_page_id"),
        )


# ---------------------------------------------------------------------------
# Page CRUD
# ---------------------------------------------------------------------------

def create_page(page: Page) -> Page:
    """Create a new page document. Slug is used as document ID."""
    if not page.owner_uids:
        raise ValueError("Page must have at least one owner")
    if page.visibility not in ("public", "personal"):
        raise ValueError("Visibility must be 'public' or 'personal'")
    db = _get_client()
    ref = db.collection(PAGES_COLLECTION).document(page.slug)
    if ref.get().exists:
        raise ValueError(f"Page '{page.slug}' already exists")
    now = _utcnow()
    page.created_at = now
    page.updated_at = now
    ref.set(page.to_dict())
    return page


def get_page(slug: str) -> Page | None:
    """Get a page by slug. Returns None if not found."""
    db = _get_client()
    doc = db.collection(PAGES_COLLECTION).document(slug).get()
    if not doc.exists:
        return None
    return Page.from_dict(slug, doc.to_dict())


def update_page(slug: str, updates: dict) -> Page:
    """Update page fields. Returns updated page."""
    db = _get_client()
    ref = db.collection(PAGES_COLLECTION).document(slug)
    doc = ref.get()
    if not doc.exists:
        raise ValueError(f"Page '{slug}' not found")
    updates["updated_at"] = _utcnow()
    ref.update(updates)
    return Page.from_dict(slug, {**doc.to_dict(), **updates})


def delete_page(slug: str) -> None:
    """Delete a page document."""
    db = _get_client()
    db.collection(PAGES_COLLECTION).document(slug).delete()


def list_pages_for_user(uid: str) -> list[Page]:
    """List all pages where uid is an owner."""
    db = _get_client()
    docs = (
        db.collection(PAGES_COLLECTION)
        .where("owner_uids", "array_contains", uid)
        .stream()
    )
    return [Page.from_dict(doc.id, doc.to_dict()) for doc in docs]


def list_ownerless_pages() -> list[Page]:
    """List all pages that have no owners (legacy/orphaned pages)."""
    db = _get_client()
    results: list[Page] = []
    for doc in db.collection(PAGES_COLLECTION).stream():
        page = Page.from_dict(doc.id, doc.to_dict())
        if not page.owner_uids:
            results.append(page)
    return results


def soft_delete_page(slug: str) -> Page:
    """Soft-delete a page: set delete_after and expire all its memories."""
    import firestore_storage
    from datetime import date as date_cls

    deadline = _utcnow() + timedelta(days=30)
    expire_date = date_cls.today() + timedelta(days=30)

    # Expire all memories on this page (use far-future today to load all)
    pairs = firestore_storage.load_memories_by_page(
        slug, today=date_cls(9999, 12, 31),
    )
    for doc_id, mem in pairs:
        mem.expires = expire_date
        firestore_storage.save_memory(mem, doc_id=doc_id)

    return update_page(slug, {"delete_after": deadline})


def restore_page(slug: str) -> Page:
    """Restore a soft-deleted page: clear delete_after, remove forced expiry."""
    import firestore_storage
    from datetime import date as date_cls

    page = get_page(slug)
    if page is None:
        raise ValueError(f"Page {slug!r} not found")
    if page.delete_after is None:
        raise ValueError(f"Page {slug!r} is not pending deletion")

    # Clear forced expiry from memories whose expires matches the deadline
    deadline_date = page.delete_after.date()
    far_future = date_cls(9999, 12, 31)
    pairs = firestore_storage.load_memories_by_page(slug, today=far_future)
    for doc_id, mem in pairs:
        if mem.expires and abs((mem.expires - deadline_date).days) <= 1:
            mem.expires = far_future
            firestore_storage.save_memory(mem, doc_id=doc_id)

    return update_page(slug, {"delete_after": None})


def add_owner(slug: str, uid: str) -> Page:
    """Add a co-owner to a page."""
    from google.cloud.firestore import ArrayUnion
    db = _get_client()
    ref = db.collection(PAGES_COLLECTION).document(slug)
    ref.update({
        "owner_uids": ArrayUnion([uid]),
        "updated_at": _utcnow(),
    })
    return get_page(slug)


def remove_owner(slug: str, uid: str) -> Page:
    """Remove an owner from a page. Raises if it would leave zero owners."""
    from google.cloud.firestore import ArrayRemove
    page = get_page(slug)
    if page is None:
        raise ValueError(f"Page '{slug}' not found")
    if uid not in page.owner_uids:
        raise ValueError(f"User '{uid}' is not an owner of page '{slug}'")
    if len(page.owner_uids) <= 1:
        raise ValueError("Cannot remove the last owner of a page")
    db = _get_client()
    ref = db.collection(PAGES_COLLECTION).document(slug)
    ref.update({
        "owner_uids": ArrayRemove([uid]),
        "updated_at": _utcnow(),
    })
    return get_page(slug)


# ---------------------------------------------------------------------------
# Invite CRUD
# ---------------------------------------------------------------------------

def create_invite(page_slug: str, created_by: str) -> Invite:
    """Create a share-link invite for a page."""
    invite_id = secrets.token_urlsafe(16)
    invite = Invite(
        invite_id=invite_id,
        page_slug=page_slug,
        created_by=created_by,
    )
    db = _get_client()
    (db.collection(PAGES_COLLECTION)
     .document(page_slug)
     .collection(INVITES_SUBCOLLECTION)
     .document(invite_id)
     .set(invite.to_dict()))
    return invite


def get_invite(page_slug: str, invite_id: str) -> Invite | None:
    """Get an invite by page slug and invite ID."""
    db = _get_client()
    doc = (
        db.collection(PAGES_COLLECTION)
        .document(page_slug)
        .collection(INVITES_SUBCOLLECTION)
        .document(invite_id)
        .get()
    )
    if not doc.exists:
        return None
    return Invite.from_dict(page_slug, doc.to_dict())


def find_invite(invite_id: str) -> Invite | None:
    """Find an invite by its ID across all pages (collection group query)."""
    db = _get_client()
    docs = (
        db.collection_group(INVITES_SUBCOLLECTION)
        .where("invite_id", "==", invite_id)
        .limit(1)
        .stream()
    )
    for doc in docs:
        # Extract page_slug from parent path: pages/{slug}/invites/{id}
        page_slug = doc.reference.parent.parent.id
        return Invite.from_dict(page_slug, doc.to_dict())
    return None


def accept_invite(invite_id: str, accepting_uid: str) -> Invite:
    """Accept an invite: add user as co-owner and mark invite as accepted.

    Raises ValueError if invite is invalid, expired, or already accepted.
    """
    invite = find_invite(invite_id)
    if invite is None:
        raise ValueError("Invite not found")
    if invite.accepted_by is not None:
        raise ValueError("Invite has already been accepted")
    now = _utcnow()
    if invite.expires_at and invite.expires_at.replace(tzinfo=timezone.utc) < now:
        raise ValueError("Invite has expired")

    # Add accepting user as owner
    add_owner(invite.page_slug, accepting_uid)

    # Mark invite as accepted
    db = _get_client()
    (db.collection(PAGES_COLLECTION)
     .document(invite.page_slug)
     .collection(INVITES_SUBCOLLECTION)
     .document(invite_id)
     .update({"accepted_by": accepting_uid}))

    invite.accepted_by = accepting_uid

    # Write audit log
    write_audit_log(
        page_slug=invite.page_slug,
        action="invite_accepted",
        actor_uid=accepting_uid,
        target_uid=accepting_uid,
        metadata={"invite_id": invite_id, "created_by": invite.created_by},
    )

    return invite


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def write_audit_log(
    page_slug: str,
    action: str,
    actor_uid: str,
    target_uid: str | None = None,
    metadata: dict | None = None,
) -> AuditLogEntry:
    """Append an entry to the audit log (server-only, append-only)."""
    entry_id = str(uuid.uuid4())
    entry = AuditLogEntry(
        entry_id=entry_id,
        page_slug=page_slug,
        action=action,
        actor_uid=actor_uid,
        target_uid=target_uid,
        metadata=metadata,
    )
    db = _get_client()
    db.collection(AUDIT_LOG_COLLECTION).document(entry_id).set(entry.to_dict())
    return entry


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

def get_or_create_user(uid: str, display_name: str | None = None, photo_url: str | None = None) -> User:
    """Get existing user profile or create one."""
    db = _get_client()
    ref = db.collection(USERS_COLLECTION).document(uid)
    doc = ref.get()
    if doc.exists:
        return User.from_dict(doc.to_dict())
    user = User(uid=uid, display_name=display_name, photo_url=photo_url)
    ref.set(user.to_dict())
    return user


def get_user(uid: str) -> User | None:
    """Get a user profile by UID."""
    db = _get_client()
    doc = db.collection(USERS_COLLECTION).document(uid).get()
    if not doc.exists:
        return None
    return User.from_dict(doc.to_dict())


def update_user(uid: str, updates: dict) -> User:
    """Update user fields."""
    db = _get_client()
    ref = db.collection(USERS_COLLECTION).document(uid)
    ref.update(updates)
    doc = ref.get()
    return User.from_dict(doc.to_dict())
