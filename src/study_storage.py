"""Firestore CRUD for cohorts, badge records, and streak snapshots.

Collections
-----------
- ``cohorts``           -- cohort definitions (name, workspace, teacher)
- ``cohort_members``    -- membership records (cohort_id + user_id)
- ``badge_records``     -- badge award records per user
- ``streak_snapshots``  -- periodic streak snapshots for analytics
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, date
from typing import Sequence

from firestore_storage import _get_client

COHORTS_COLLECTION = "cohorts"
COHORT_MEMBERS_COLLECTION = "cohort_members"
BADGE_RECORDS_COLLECTION = "badge_records"
STREAK_SNAPSHOTS_COLLECTION = "streak_snapshots"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_cohort(
    workspace_id: str,
    title: str,
    created_by: str,
    description: str | None = None,
    cohort_id: str | None = None,
) -> dict:
    db = _get_client()
    cid = cohort_id or str(uuid.uuid4())
    now = _utcnow()
    doc = {
        "cohort_id": cid,
        "workspace_id": workspace_id,
        "title": title,
        "description": description,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    db.collection(COHORTS_COLLECTION).document(cid).set(doc)
    return doc


def get_cohort(cohort_id: str) -> dict | None:
    db = _get_client()
    doc = db.collection(COHORTS_COLLECTION).document(cohort_id).get()
    if not doc.exists:
        return None
    return doc.to_dict()


def list_cohorts_for_workspace(workspace_id: str) -> list[dict]:
    db = _get_client()
    docs = (
        db.collection(COHORTS_COLLECTION)
        .where("workspace_id", "==", workspace_id)
        .stream()
    )
    results = [d.to_dict() for d in docs]
    results.sort(key=lambda c: c.get("created_at") or datetime.min.replace(tzinfo=timezone.utc))
    return results


def delete_cohort(cohort_id: str) -> None:
    db = _get_client()
    db.collection(COHORTS_COLLECTION).document(cohort_id).delete()


def add_cohort_member(
    cohort_id: str,
    user_id: str,
    role: str = "student",
) -> dict:
    db = _get_client()
    member_doc_id = f"{cohort_id}:{user_id}"
    now = _utcnow()
    doc = {
        "member_id": member_doc_id,
        "cohort_id": cohort_id,
        "user_id": user_id,
        "role": role,
        "joined_at": now,
    }
    db.collection(COHORT_MEMBERS_COLLECTION).document(member_doc_id).set(doc, merge=True)
    return doc


def remove_cohort_member(cohort_id: str, user_id: str) -> None:
    db = _get_client()
    member_doc_id = f"{cohort_id}:{user_id}"
    db.collection(COHORT_MEMBERS_COLLECTION).document(member_doc_id).delete()


def list_cohort_members(cohort_id: str) -> list[dict]:
    db = _get_client()
    docs = (
        db.collection(COHORT_MEMBERS_COLLECTION)
        .where("cohort_id", "==", cohort_id)
        .stream()
    )
    return [d.to_dict() for d in docs]


def get_cohort_member(cohort_id: str, user_id: str) -> dict | None:
    db = _get_client()
    doc = db.collection(COHORT_MEMBERS_COLLECTION).document(f"{cohort_id}:{user_id}").get()
    if not doc.exists:
        return None
    return doc.to_dict()


def save_badge(
    user_id: str,
    workspace_id: str,
    badge_id: str,
    label: str,
    awarded_on: date | None = None,
) -> dict:
    db = _get_client()
    doc_id = f"{user_id}:{badge_id}"
    today = awarded_on or _utcnow().date()
    doc = {
        "record_id": doc_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "badge_id": badge_id,
        "label": label,
        "awarded_on": today.isoformat() if hasattr(today, "isoformat") else str(today),
        "created_at": _utcnow(),
    }
    db.collection(BADGE_RECORDS_COLLECTION).document(doc_id).set(doc, merge=True)
    return doc


def list_badges_for_user(user_id: str, workspace_id: str | None = None) -> list[dict]:
    db = _get_client()
    query = db.collection(BADGE_RECORDS_COLLECTION).where("user_id", "==", user_id)
    if workspace_id is not None:
        query = query.where("workspace_id", "==", workspace_id)
    docs = query.stream()
    return [d.to_dict() for d in docs]


def save_streak_snapshot(
    user_id: str,
    workspace_id: str,
    current_streak: int,
    longest_streak: int,
    total_confirmed: int,
    snapshot_date: date | None = None,
) -> dict:
    db = _get_client()
    today = snapshot_date or _utcnow().date()
    doc_id = f"{user_id}:{workspace_id}:{today.isoformat()}"
    doc = {
        "snapshot_id": doc_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_confirmed": total_confirmed,
        "snapshot_date": today.isoformat(),
        "created_at": _utcnow(),
    }
    db.collection(STREAK_SNAPSHOTS_COLLECTION).document(doc_id).set(doc, merge=True)
    return doc


def get_latest_streak_snapshot(user_id: str, workspace_id: str) -> dict | None:
    db = _get_client()
    docs = list(
        db.collection(STREAK_SNAPSHOTS_COLLECTION)
        .where("user_id", "==", user_id)
        .where("workspace_id", "==", workspace_id)
        .order_by("snapshot_date", direction="DESCENDING")
        .limit(1)
        .stream()
    )
    if not docs:
        return None
    return docs[0].to_dict()
