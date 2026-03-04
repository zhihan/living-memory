"""Firestore-backed storage for memories."""

from __future__ import annotations

import os
from datetime import date

from dates import today as _today
from memory import Memory

COLLECTION = "memories"


def _get_client():
    """Return a Firestore client (lazy import to avoid import-time errors).

    Respects ``LIVING_MEMORY_FIRESTORE_DATABASE`` to select a non-default
    database and ``GOOGLE_CLOUD_PROJECT`` for the project ID.
    """
    from google.cloud import firestore

    kwargs: dict[str, str] = {}
    database = os.environ.get("LIVING_MEMORY_FIRESTORE_DATABASE")
    if database:
        kwargs["database"] = database
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        kwargs["project"] = project
    return firestore.Client(**kwargs)


def save_memory(memory: Memory, doc_id: str | None = None) -> str:
    """Save a memory to Firestore. Returns the document ID.

    If *doc_id* is provided the document is overwritten (update);
    otherwise a new document with an auto-generated ID is created.
    """
    db = _get_client()
    data = memory.to_dict()
    if doc_id:
        db.collection(COLLECTION).document(doc_id).set(data)
        return doc_id
    _, ref = db.collection(COLLECTION).add(data)
    return ref.id


def _load_memories_where(
    field: str, value: str, today: date | None = None,
) -> list[tuple[str, Memory]]:
    """Load non-expired memories matching a single field filter."""
    if today is None:
        today = _today()
    db = _get_client()
    docs = db.collection(COLLECTION).where(field, "==", value).stream()
    results: list[tuple[str, Memory]] = []
    for doc in docs:
        mem = Memory.from_dict(doc.to_dict())
        if not mem.is_expired(today):
            results.append((doc.id, mem))
    return results


def load_memories(user_id: str, today: date | None = None) -> list[tuple[str, Memory]]:
    """Load non-expired memories for a given user.

    Returns a list of ``(doc_id, Memory)`` tuples.
    Expiry is checked client-side to match ``Memory.is_expired`` semantics
    (expired when ``today > expires``, so ``today == expires`` is still valid).
    """
    return _load_memories_where("user_id", user_id, today)


def load_all_memories() -> list[tuple[str, Memory]]:
    """Load every memory document (admin/migration use).

    Returns a list of ``(doc_id, Memory)`` tuples.
    """
    db = _get_client()
    results: list[tuple[str, Memory]] = []
    for doc in db.collection(COLLECTION).stream():
        mem = Memory.from_dict(doc.to_dict())
        results.append((doc.id, mem))
    return results


def delete_memory(doc_id: str) -> None:
    """Delete a single memory document by its Firestore ID."""
    db = _get_client()
    db.collection(COLLECTION).document(doc_id).delete()


def delete_expired(today: date | None = None) -> list[tuple[str, Memory]]:
    """Find and delete all expired memory documents.

    Returns a list of ``(doc_id, Memory)`` tuples for deleted documents
    (so callers can purge attachments, etc.).
    """
    if today is None:
        today = _today()
    db = _get_client()
    all_docs = db.collection(COLLECTION).stream()
    deleted: list[tuple[str, Memory]] = []
    for doc in all_docs:
        mem = Memory.from_dict(doc.to_dict())
        if mem.is_expired(today):
            doc.reference.delete()
            deleted.append((doc.id, mem))
    return deleted


def _find_memory_by_title_where(
    field: str, value: str, title: str, today: date | None = None,
) -> tuple[str, Memory] | None:
    """Find a non-expired memory matching *title* filtered by a single field."""
    for doc_id, mem in _load_memories_where(field, value, today):
        if mem.title == title:
            return doc_id, mem
    return None


def find_memory_by_title(
    user_id: str, title: str, today: date | None = None,
) -> tuple[str, Memory] | None:
    """Find a non-expired memory matching *title* for *user_id*.

    Returns ``(doc_id, Memory)`` or ``None``.
    """
    return _find_memory_by_title_where("user_id", user_id, title, today)


# ---------------------------------------------------------------------------
# Page-scoped memory operations
# ---------------------------------------------------------------------------

def load_memories_by_page(
    page_id: str, today: date | None = None,
) -> list[tuple[str, Memory]]:
    """Load non-expired memories for a given page.

    Returns a list of ``(doc_id, Memory)`` tuples.
    """
    return _load_memories_where("page_id", page_id, today)


def find_memory_by_title_on_page(
    page_id: str, title: str, today: date | None = None,
) -> tuple[str, Memory] | None:
    """Find a non-expired memory matching *title* on a page.

    Returns ``(doc_id, Memory)`` or ``None``.
    """
    return _find_memory_by_title_where("page_id", page_id, title, today)


def get_memory(doc_id: str) -> Memory | None:
    """Get a single memory by document ID. Returns None if not found."""
    db = _get_client()
    doc = db.collection(COLLECTION).document(doc_id).get()
    if not doc.exists:
        return None
    return Memory.from_dict(doc.to_dict())
