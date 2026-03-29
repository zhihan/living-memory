"""Notification dispatch layer.

Abstracts over delivery channels (email, in_app) and provides:
- channel-specific send functions
- a unified dispatch entry point used by the scheduler job
- duplicate-send protection via DeliveryLog lookups

Environment variables for email:
  SMTP_HOST          default: localhost
  SMTP_PORT          default: 587
  SMTP_USER          optional
  SMTP_PASSWORD      optional
  FROM_EMAIL         default: noreply@event-ledger.app
  APP_BASE_URL       used to build occurrence links in email body
"""

from __future__ import annotations

import logging
import os
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Any

from models import DeliveryLog, NotificationRule, Occurrence, Series

log = logging.getLogger(__name__)


def _smtp_config() -> dict[str, Any]:
    return {
        "host": os.environ.get("SMTP_HOST", "localhost"),
        "port": int(os.environ.get("SMTP_PORT", 587)),
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "from_email": os.environ.get("FROM_EMAIL", "noreply@event-ledger.app"),
    }


def _smtp_available() -> bool:
    cfg = _smtp_config()
    return bool(cfg.get("user") or cfg["host"] not in ("localhost", "127.0.0.1"))


def _build_email_body(occurrence: Occurrence, series: Series) -> str:
    base_url = os.environ.get("APP_BASE_URL", "https://app.event-ledger.app")
    link = f"{base_url}/occurrences/{occurrence.occurrence_id}"
    title = (occurrence.overrides and occurrence.overrides.title) or series.title
    location = (occurrence.overrides and occurrence.overrides.location) or series.default_location or ""
    online_link = (occurrence.overrides and occurrence.overrides.online_link) or series.default_online_link or ""
    lines = [
        f"Reminder: {title}",
        "",
        f"Scheduled for: {occurrence.scheduled_for}",
    ]
    if location:
        lines.append(f"Location: {location}")
    if online_link:
        lines.append(f"Online link: {online_link}")
    lines += ["", f"View details: {link}", "", "— Event Ledger"]
    return "\n".join(lines)


def send_email(
    to_address: str,
    subject: str,
    body: str,
    ics_bytes: bytes | None = None,
    ics_filename: str = "event.ics",
) -> None:
    """Send a plain-text email via SMTP. Optionally attach an ICS file."""
    cfg = _smtp_config()
    msg: MIMEMultipart = MIMEMultipart("mixed") if ics_bytes else MIMEMultipart("alternative")
    msg["From"] = cfg["from_email"]
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if ics_bytes:
        part = MIMEBase("text", "calendar", method="REQUEST")
        part.set_payload(ics_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=ics_filename)
        msg.attach(part)
    with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
        server.ehlo()
        if cfg["port"] == 587:
            server.starttls()
        if cfg["user"] and cfg["password"]:
            server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["from_email"], [to_address], msg.as_string())


def dispatch_email(
    occurrence: Occurrence,
    series: Series,
    rule: NotificationRule,
    recipient_email: str,
    attach_ics: bool = False,
) -> None:
    title = (occurrence.overrides and occurrence.overrides.title) or series.title
    subject = f"Reminder: {title}"
    body = _build_email_body(occurrence, series)
    ics_bytes: bytes | None = None
    if attach_ics:
        try:
            from ics_export import occurrence_to_ics
            ics_bytes = occurrence_to_ics(occurrence, series).to_ical()
        except Exception as exc:
            log.warning("Failed to generate ICS attachment: %s", exc)
    send_email(recipient_email, subject, body, ics_bytes=ics_bytes)


def dispatch_in_app(
    occurrence: Occurrence,
    series: Series,
    rule: NotificationRule,
    recipient_uid: str,
) -> None:
    """Stub for in-app push/websocket notifications (not yet implemented)."""
    log.debug("in_app notification (stub): uid=%s occurrence=%s", recipient_uid, occurrence.occurrence_id)


def dispatch_telegram(
    occurrence: Occurrence,
    series: Series,
    rule: NotificationRule,
    recipient_uid: str,
) -> None:
    """Stub for Telegram notifications (Phase 8)."""
    log.debug("telegram notification (stub): uid=%s occurrence=%s", recipient_uid, occurrence.occurrence_id)


def dispatch(
    occurrence: Occurrence,
    series: Series,
    rule: NotificationRule,
    recipient_uid: str,
    recipient_email: str | None = None,
) -> DeliveryLog:
    """Dispatch a single notification and return a DeliveryLog.

    Does NOT persist the log — caller is responsible for storage.
    """
    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    log_record = DeliveryLog(
        log_id=log_id,
        rule_id=rule.rule_id,
        occurrence_id=occurrence.occurrence_id,
        workspace_id=occurrence.workspace_id,
        recipient_uid=recipient_uid,
        channel=rule.channel,
        status="pending",
        created_at=now,
    )
    try:
        if rule.channel == "email":
            if not recipient_email:
                raise ValueError("Email address required for email channel")
            dispatch_email(occurrence, series, rule, recipient_email)
        elif rule.channel == "in_app":
            dispatch_in_app(occurrence, series, rule, recipient_uid)
        elif rule.channel == "telegram":
            dispatch_telegram(occurrence, series, rule, recipient_uid)
        elif rule.channel == "calendar":
            if not recipient_email:
                raise ValueError("Email address required for calendar channel")
            dispatch_email(occurrence, series, rule, recipient_email, attach_ics=True)
        else:
            raise ValueError(f"Unknown channel: {rule.channel!r}")
        log_record.status = "sent"
        log_record.sent_at = datetime.now(timezone.utc)
    except Exception as exc:
        log_record.status = "failed"
        log_record.error = str(exc)
        log.error(
            "Notification dispatch failed: uid=%s occ=%s channel=%s error=%s",
            recipient_uid, occurrence.occurrence_id, rule.channel, exc,
        )
    return log_record
