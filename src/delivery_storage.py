"""Delivery storage — higher-level queries for DeliveryLog operations.

Provides the queries needed by the notification scheduler:
- has_been_delivered: duplicate-send guard
- list_failed_logs_for_retry: find failed logs eligible for retry
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from models import DeliveryLog
import series_storage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def has_been_delivered(
    rule_id: str,
    occurrence_id: str,
    recipient_uid: str,
) -> bool:
    """Return True if a sent DeliveryLog already exists for this triple.

    Prevents duplicate notifications when the scheduler runs multiple times.
    """
    from firestore_storage import _get_client
    db = _get_client()
    docs = (
        db.collection(series_storage.DELIVERY_LOGS_COLLECTION)
        .where("rule_id", "==", rule_id)
        .where("occurrence_id", "==", occurrence_id)
        .where("recipient_uid", "==", recipient_uid)
        .where("status", "==", "sent")
        .limit(1)
        .stream()
    )
    for _ in docs:
        return True
    return False


def list_failed_logs_for_retry(
    max_age_hours: int = 24,
    limit: int = 100,
) -> list[DeliveryLog]:
    """Return failed DeliveryLogs created within the last max_age_hours."""
    from firestore_storage import _get_client
    db = _get_client()
    cutoff = _utcnow() - timedelta(hours=max_age_hours)
    docs = (
        db.collection(series_storage.DELIVERY_LOGS_COLLECTION)
        .where("status", "==", "failed")
        .where("created_at", ">=", cutoff)
        .limit(limit)
        .stream()
    )
    return [DeliveryLog.from_dict(doc.to_dict()) for doc in docs]


def append_delivery_log(log: DeliveryLog) -> DeliveryLog:
    """Persist a DeliveryLog entry (immutable append)."""
    return series_storage.append_delivery_log(log)


def list_delivery_logs_for_occurrence(occurrence_id: str) -> list[DeliveryLog]:
    """Return all delivery log entries for a specific Occurrence."""
    return series_storage.list_delivery_logs_for_occurrence(occurrence_id)


def list_delivery_logs_for_workspace(
    workspace_id: str,
    limit: int = 200,
) -> list[DeliveryLog]:
    """Return recent DeliveryLogs for a workspace (newest first)."""
    from firestore_storage import _get_client
    db = _get_client()
    docs = (
        db.collection(series_storage.DELIVERY_LOGS_COLLECTION)
        .where("workspace_id", "==", workspace_id)
        .limit(limit)
        .stream()
    )
    results = [DeliveryLog.from_dict(doc.to_dict()) for doc in docs]
    results.sort(
        key=lambda d: d.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return results
