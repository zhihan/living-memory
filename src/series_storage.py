"""Firestore-backed storage for Series, Occurrences, CheckIns, and delivery logs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from firestore_storage import _get_client
from models import CheckIn, DeliveryLog, NotificationRule, Occurrence, Series

SERIES_COLLECTION = "series"
OCCURRENCES_COLLECTION = "occurrences"
CHECK_INS_COLLECTION = "check_ins"
NOTIFICATION_RULES_COLLECTION = "notification_rules"
DELIVERY_LOGS_COLLECTION = "delivery_logs"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Series CRUD
# ---------------------------------------------------------------------------

def create_series(series: Series) -> Series:
    """Persist a new Series. series_id is used as the Firestore document ID."""
    db = _get_client()
    ref = db.collection(SERIES_COLLECTION).document(series.series_id)
    if ref.get().exists:
        raise ValueError(f"Series already exists: {series.series_id}")
    now = _utcnow()
    series.created_at = now
    series.updated_at = now
    ref.set(series.to_dict())
    return series


def get_series(series_id: str) -> Series | None:
    """Fetch a Series by ID. Returns None if not found."""
    db = _get_client()
    doc = db.collection(SERIES_COLLECTION).document(series_id).get()
    if not doc.exists:
        return None
    return Series.from_dict(doc.to_dict())


def update_series(series_id: str, updates: dict) -> Series:
    """Apply partial updates to a Series. Raises if not found."""
    db = _get_client()
    ref = db.collection(SERIES_COLLECTION).document(series_id)
    doc = ref.get()
    if not doc.exists:
        raise ValueError(f"Series not found: {series_id}")
    updates["updated_at"] = _utcnow()
    ref.update(updates)
    return Series.from_dict({**doc.to_dict(), **updates})


def delete_series(series_id: str) -> None:
    """Hard-delete a Series document."""
    db = _get_client()
    db.collection(SERIES_COLLECTION).document(series_id).delete()


def list_series_for_workspace(workspace_id: str) -> list[Series]:
    """Return all Series belonging to workspace_id, ordered by created_at."""
    db = _get_client()
    docs = (
        db.collection(SERIES_COLLECTION)
        .where("workspace_id", "==", workspace_id)
        .stream()
    )
    results = [Series.from_dict(doc.to_dict()) for doc in docs]
    results.sort(key=lambda s: s.created_at or datetime.min.replace(tzinfo=timezone.utc))
    return results


# ---------------------------------------------------------------------------
# Occurrence CRUD
# ---------------------------------------------------------------------------

def save_occurrence(occurrence: Occurrence) -> Occurrence:
    """Upsert an Occurrence. occurrence_id is the Firestore document ID."""
    db = _get_client()
    now = _utcnow()
    if occurrence.created_at is None:
        occurrence.created_at = now
    occurrence.updated_at = now
    db.collection(OCCURRENCES_COLLECTION).document(occurrence.occurrence_id).set(
        occurrence.to_dict()
    )
    return occurrence


def get_occurrence(occurrence_id: str) -> Occurrence | None:
    """Fetch an Occurrence by ID. Returns None if not found."""
    db = _get_client()
    doc = db.collection(OCCURRENCES_COLLECTION).document(occurrence_id).get()
    if not doc.exists:
        return None
    return Occurrence.from_dict(doc.to_dict())


def update_occurrence(occurrence_id: str, updates: dict) -> Occurrence:
    """Apply partial updates to an Occurrence. Raises if not found."""
    db = _get_client()
    ref = db.collection(OCCURRENCES_COLLECTION).document(occurrence_id)
    doc = ref.get()
    if not doc.exists:
        raise ValueError(f"Occurrence not found: {occurrence_id}")
    updates["updated_at"] = _utcnow()
    ref.update(updates)
    return Occurrence.from_dict({**doc.to_dict(), **updates})


def delete_occurrence(occurrence_id: str) -> None:
    """Hard-delete an Occurrence document."""
    db = _get_client()
    db.collection(OCCURRENCES_COLLECTION).document(occurrence_id).delete()


def list_occurrences_for_series(
    series_id: str,
    status: str | None = None,
) -> list[Occurrence]:
    """Return Occurrences for a Series, optionally filtered by status."""
    db = _get_client()
    query = db.collection(OCCURRENCES_COLLECTION).where("series_id", "==", series_id)
    if status is not None:
        query = query.where("status", "==", status)
    docs = query.stream()
    results = [Occurrence.from_dict(doc.to_dict()) for doc in docs]
    results.sort(key=lambda o: o.scheduled_for)
    return results


def list_occurrences_for_workspace(
    workspace_id: str,
    status: str | None = None,
) -> list[Occurrence]:
    """Return Occurrences for a workspace, optionally filtered by status."""
    db = _get_client()
    query = (
        db.collection(OCCURRENCES_COLLECTION)
        .where("workspace_id", "==", workspace_id)
    )
    if status is not None:
        query = query.where("status", "==", status)
    docs = query.stream()
    results = [Occurrence.from_dict(doc.to_dict()) for doc in docs]
    results.sort(key=lambda o: o.scheduled_for)
    return results


def save_occurrences_batch(occurrences: Sequence[Occurrence]) -> None:
    """Batch-write a list of Occurrences in a single Firestore transaction."""
    if not occurrences:
        return
    db = _get_client()
    batch = db.batch()
    now = _utcnow()
    for occ in occurrences:
        if occ.created_at is None:
            occ.created_at = now
        occ.updated_at = now
        ref = db.collection(OCCURRENCES_COLLECTION).document(occ.occurrence_id)
        batch.set(ref, occ.to_dict())
    batch.commit()


# ---------------------------------------------------------------------------
# CheckIn CRUD
# ---------------------------------------------------------------------------

def save_check_in(check_in: CheckIn) -> CheckIn:
    """Upsert a CheckIn."""
    db = _get_client()
    now = _utcnow()
    if check_in.created_at is None:
        check_in.created_at = now
    check_in.updated_at = now
    db.collection(CHECK_INS_COLLECTION).document(check_in.check_in_id).set(
        check_in.to_dict()
    )
    return check_in


def get_check_in(check_in_id: str) -> CheckIn | None:
    """Fetch a CheckIn by ID. Returns None if not found."""
    db = _get_client()
    doc = db.collection(CHECK_INS_COLLECTION).document(check_in_id).get()
    if not doc.exists:
        return None
    return CheckIn.from_dict(doc.to_dict())


def list_check_ins_for_occurrence(occurrence_id: str) -> list[CheckIn]:
    """Return all CheckIns for a specific Occurrence."""
    db = _get_client()
    docs = (
        db.collection(CHECK_INS_COLLECTION)
        .where("occurrence_id", "==", occurrence_id)
        .stream()
    )
    return [CheckIn.from_dict(doc.to_dict()) for doc in docs]


def get_check_in_for_user(occurrence_id: str, user_id: str) -> CheckIn | None:
    """Return the CheckIn for a specific user on a specific Occurrence, or None."""
    db = _get_client()
    docs = (
        db.collection(CHECK_INS_COLLECTION)
        .where("occurrence_id", "==", occurrence_id)
        .where("user_id", "==", user_id)
        .limit(1)
        .stream()
    )
    for doc in docs:
        return CheckIn.from_dict(doc.to_dict())
    return None


# ---------------------------------------------------------------------------
# NotificationRule CRUD
# ---------------------------------------------------------------------------

def save_notification_rule(rule: NotificationRule) -> NotificationRule:
    """Upsert a NotificationRule."""
    db = _get_client()
    now = _utcnow()
    if rule.created_at is None:
        rule.created_at = now
    rule.updated_at = now
    db.collection(NOTIFICATION_RULES_COLLECTION).document(rule.rule_id).set(
        rule.to_dict()
    )
    return rule


def get_notification_rule(rule_id: str) -> NotificationRule | None:
    """Fetch a NotificationRule by ID."""
    db = _get_client()
    doc = db.collection(NOTIFICATION_RULES_COLLECTION).document(rule_id).get()
    if not doc.exists:
        return None
    return NotificationRule.from_dict(doc.to_dict())


def list_notification_rules_for_workspace(workspace_id: str) -> list[NotificationRule]:
    """Return all enabled NotificationRules for a workspace."""
    db = _get_client()
    docs = (
        db.collection(NOTIFICATION_RULES_COLLECTION)
        .where("workspace_id", "==", workspace_id)
        .stream()
    )
    return [NotificationRule.from_dict(doc.to_dict()) for doc in docs]


# ---------------------------------------------------------------------------
# DeliveryLog (append-only)
# ---------------------------------------------------------------------------

def append_delivery_log(log: DeliveryLog) -> DeliveryLog:
    """Write an immutable DeliveryLog entry."""
    db = _get_client()
    now = _utcnow()
    if log.created_at is None:
        log.created_at = now
    db.collection(DELIVERY_LOGS_COLLECTION).document(log.log_id).set(log.to_dict())
    return log


def list_delivery_logs_for_occurrence(occurrence_id: str) -> list[DeliveryLog]:
    """Return all delivery log entries for a specific Occurrence."""
    db = _get_client()
    docs = (
        db.collection(DELIVERY_LOGS_COLLECTION)
        .where("occurrence_id", "==", occurrence_id)
        .stream()
    )
    results = [DeliveryLog.from_dict(doc.to_dict()) for doc in docs]
    results.sort(key=lambda d: d.created_at or datetime.min.replace(tzinfo=timezone.utc))
    return results
