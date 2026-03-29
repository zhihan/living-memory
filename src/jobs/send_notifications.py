"""Notification scheduler job.

Runnable as: python -m src.jobs.send_notifications
"""
from __future__ import annotations
import logging, os, sys
from datetime import datetime, timedelta, timezone

if __name__ == "__main__":
    import pathlib
    _here = pathlib.Path(__file__).resolve().parent.parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))

import delivery_storage, notifications, series_storage, workspace_storage
from models import NotificationRule, Occurrence, Series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("send_notifications")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_user_email(uid: str) -> str | None:
    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        user = firebase_auth.get_user(uid)
        return user.email or None
    except Exception as exc:
        log.debug("Could not look up email for uid=%s: %s", uid, exc)
        return None


def _occurrences_in_window(workspace_id: str, rule: NotificationRule, now: datetime) -> list[Occurrence]:
    """Return scheduled occurrences whose send-window is open for rule.

    Window open when: now < scheduled_for <= now + remind_before_minutes
    """
    window_end = now + timedelta(minutes=rule.remind_before_minutes)
    all_occs = series_storage.list_occurrences_for_workspace(workspace_id, status="scheduled")
    result: list[Occurrence] = []
    for occ in all_occs:
        if rule.series_id and occ.series_id != rule.series_id:
            continue
        try:
            occ_dt = datetime.fromisoformat(occ.scheduled_for)
        except ValueError:
            continue
        if occ_dt.tzinfo is None:
            occ_dt = occ_dt.replace(tzinfo=timezone.utc)
        if now < occ_dt <= window_end:
            result.append(occ)
    return result


def _members_for_rule(workspace: object, rule: NotificationRule) -> list[str]:
    """Return UIDs matching rule target_roles. Empty = all members."""
    member_roles: dict[str, str] = getattr(workspace, "member_roles", {})
    if not rule.target_roles:
        return list(member_roles.keys())
    return [uid for uid, role in member_roles.items() if role in rule.target_roles]


def run_scheduler(lookahead_minutes: int | None = None) -> dict[str, int]:
    """Execute one scheduler pass. Returns {dispatched, skipped, failed}."""
    if lookahead_minutes is None:
        lookahead_minutes = int(os.environ.get("NOTIFICATION_LOOKAHEAD_MINUTES", 60))
    now = _utcnow()
    summary = {"dispatched": 0, "skipped": 0, "failed": 0}
    from firestore_storage import _get_client
    db = _get_client()
    workspace_docs = db.collection(workspace_storage.WORKSPACES_COLLECTION).stream()
    for ws_doc in workspace_docs:
        ws_data = ws_doc.to_dict()
        workspace_id = ws_data.get("workspace_id", ws_doc.id)
        rules = series_storage.list_notification_rules_for_workspace(workspace_id)
        enabled_rules = [r for r in rules if r.enabled]
        if not enabled_rules:
            continue
        workspace = workspace_storage.get_workspace(workspace_id)
        if workspace is None:
            continue
        for rule in enabled_rules:
            occs = _occurrences_in_window(workspace_id, rule, now)
            for occ in occs:
                s = series_storage.get_series(occ.series_id)
                if s is None:
                    log.warning("Series not found for occ=%s", occ.occurrence_id)
                    continue
                members = _members_for_rule(workspace, rule)
                for uid in members:
                    if delivery_storage.has_been_delivered(rule.rule_id, occ.occurrence_id, uid):
                        summary["skipped"] += 1
                        continue
                    email = _get_user_email(uid) if rule.channel in ("email", "calendar") else None
                    dl = notifications.dispatch(occurrence=occ, series=s, rule=rule, recipient_uid=uid, recipient_email=email)
                    delivery_storage.append_delivery_log(dl)
                    if dl.status == "sent":
                        summary["dispatched"] += 1
                    else:
                        summary["failed"] += 1
                        log.warning("Dispatch failed rule=%s occ=%s uid=%s err=%s", rule.rule_id, occ.occurrence_id, uid, dl.error)
    log.info("Scheduler pass complete: dispatched=%d skipped=%d failed=%d", summary["dispatched"], summary["skipped"], summary["failed"])
    return summary


def run_retry_pass(max_age_hours: int = 24) -> dict[str, int]:
    """Re-attempt delivery for recently-failed logs."""
    failed_logs = delivery_storage.list_failed_logs_for_retry(max_age_hours=max_age_hours)
    summary = {"retried": 0, "succeeded": 0, "still_failed": 0}
    for failed in failed_logs:
        occ = series_storage.get_occurrence(failed.occurrence_id)
        if occ is None:
            continue
        s = series_storage.get_series(occ.series_id)
        if s is None:
            continue
        rule = series_storage.get_notification_rule(failed.rule_id)
        if rule is None:
            continue
        email = _get_user_email(failed.recipient_uid) if rule.channel in ("email", "calendar") else None
        dl = notifications.dispatch(occurrence=occ, series=s, rule=rule, recipient_uid=failed.recipient_uid, recipient_email=email)
        delivery_storage.append_delivery_log(dl)
        summary["retried"] += 1
        if dl.status == "sent":
            summary["succeeded"] += 1
        else:
            summary["still_failed"] += 1
    log.info("Retry pass complete: retried=%d succeeded=%d still_failed=%d", summary["retried"], summary["succeeded"], summary["still_failed"])
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Event Ledger notification scheduler")
    parser.add_argument("--lookahead", type=int, default=None)
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--retry-max-age-hours", type=int, default=24)
    args = parser.parse_args()
    result = run_scheduler(lookahead_minutes=args.lookahead)
    print("Scheduler:", result)
    if args.retry:
        retry_result = run_retry_pass(max_age_hours=args.retry_max_age_hours)
        print("Retry:", retry_result)
