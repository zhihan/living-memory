"""Domain models for the pivot to a recurring-schedule platform.

New vocabulary:
- Workspace  (replaces Page)
- Series     (a recurring schedule)
- Occurrence (a single instance of a Series)
- CheckIn    (participant attendance/confirmation)
- NotificationRule  (per-workspace delivery preferences)
- DeliveryLog       (immutable record of a sent notification)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Literal types
# ---------------------------------------------------------------------------

WorkspaceType = Literal["personal", "shared", "study"]
SeriesKind = Literal["reminder", "meeting", "study_assignment"]
SeriesStatus = Literal["active", "paused", "archived"]
OccurrenceStatus = Literal["scheduled", "cancelled", "completed", "rescheduled"]
CheckInStatus = Literal["pending", "confirmed", "declined", "missed"]
MemberRole = Literal["organizer", "participant", "teacher", "assistant", "student"]
NotificationChannel = Literal["email", "in_app", "telegram", "calendar"]
DeliveryStatus = Literal["pending", "sent", "failed", "skipped"]


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

@dataclass
class Workspace:
    """Top-level container for a group of related recurring schedules.

    Maps to the Firestore ``workspaces`` collection.
    """

    workspace_id: str
    title: str
    type: WorkspaceType
    timezone: str
    owner_uids: list[str]
    # uid -> MemberRole; owners are also listed here with role "organizer"
    member_roles: dict[str, MemberRole] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    description: str | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "workspace_id": self.workspace_id,
            "title": self.title,
            "type": self.type,
            "timezone": self.timezone,
            "owner_uids": self.owner_uids,
            "member_roles": self.member_roles,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Workspace:
        return cls(
            workspace_id=data["workspace_id"],
            title=data["title"],
            type=data["type"],
            timezone=data.get("timezone", "UTC"),
            owner_uids=list(data.get("owner_uids", [])),
            member_roles=dict(data.get("member_roles", {})),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            description=data.get("description"),
        )


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

@dataclass
class ScheduleRule:
    """Serializable recurrence rule.

    ``frequency`` is one of:
      - ``"daily"``     — every day
      - ``"weekly"``    — every week on ``weekdays``
      - ``"weekdays"``  — Monday–Friday
      - ``"custom"``    — specific weekday list (same as weekly but explicit)
      - ``"once"``      — no recurrence (single-shot)

    ``weekdays`` is a list of ISO weekday integers (1=Monday … 7=Sunday).
    For ``daily`` and ``weekdays`` frequency, ``weekdays`` is ignored.

    ``interval`` is how many units to skip between occurrences (default 1).
    For example ``interval=2`` with ``frequency="weekly"`` means every two weeks.

    ``until`` is an optional UTC datetime after which no new occurrences
    should be generated.

    ``count`` is an optional cap on the total number of occurrences to generate.
    """

    frequency: Literal["daily", "weekly", "weekdays", "custom", "once"]
    weekdays: list[int] = field(default_factory=list)  # 1=Mon … 7=Sun
    interval: int = 1
    until: datetime | None = None
    count: int | None = None

    def to_dict(self) -> dict:
        return {
            "frequency": self.frequency,
            "weekdays": self.weekdays,
            "interval": self.interval,
            "until": self.until.isoformat() if self.until else None,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScheduleRule:
        until_raw = data.get("until")
        return cls(
            frequency=data["frequency"],
            weekdays=list(data.get("weekdays", [])),
            interval=int(data.get("interval", 1)),
            until=datetime.fromisoformat(until_raw) if until_raw else None,
            count=data.get("count"),
        )


@dataclass
class Series:
    """A recurring schedule owned by a Workspace.

    Maps to the Firestore ``series`` collection.
    """

    series_id: str
    workspace_id: str
    kind: SeriesKind
    title: str
    schedule_rule: ScheduleRule
    # Wall-clock time of day: "HH:MM" in the workspace's timezone
    default_time: str | None = None
    default_duration_minutes: int | None = None
    default_location: str | None = None
    default_online_link: str | None = None
    status: SeriesStatus = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    description: str | None = None
    # UID of the user who created this series
    created_by: str | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "series_id": self.series_id,
            "workspace_id": self.workspace_id,
            "kind": self.kind,
            "title": self.title,
            "schedule_rule": self.schedule_rule.to_dict(),
            "default_time": self.default_time,
            "default_duration_minutes": self.default_duration_minutes,
            "default_location": self.default_location,
            "default_online_link": self.default_online_link,
            "status": self.status,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
            "description": self.description,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Series:
        return cls(
            series_id=data["series_id"],
            workspace_id=data["workspace_id"],
            kind=data["kind"],
            title=data["title"],
            schedule_rule=ScheduleRule.from_dict(data["schedule_rule"]),
            default_time=data.get("default_time"),
            default_duration_minutes=data.get("default_duration_minutes"),
            default_location=data.get("default_location"),
            default_online_link=data.get("default_online_link"),
            status=data.get("status", "active"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            description=data.get("description"),
            created_by=data.get("created_by"),
        )


# ---------------------------------------------------------------------------
# Occurrence
# ---------------------------------------------------------------------------

@dataclass
class OccurrenceOverrides:
    """Fields that can be changed on a single occurrence without affecting the series."""

    time: str | None = None
    duration_minutes: int | None = None
    location: str | None = None
    online_link: str | None = None
    title: str | None = None

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "duration_minutes": self.duration_minutes,
            "location": self.location,
            "online_link": self.online_link,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OccurrenceOverrides:
        return cls(
            time=data.get("time"),
            duration_minutes=data.get("duration_minutes"),
            location=data.get("location"),
            online_link=data.get("online_link"),
            title=data.get("title"),
        )


@dataclass
class Occurrence:
    """A single scheduled instance of a Series.

    Maps to the Firestore ``occurrences`` collection.
    ``scheduled_for`` is an ISO 8601 UTC datetime string representing the
    start of this occurrence.  Effective wall-clock time is determined by
    either ``overrides.time`` or ``Series.default_time`` plus the workspace
    timezone.
    """

    occurrence_id: str
    series_id: str
    workspace_id: str
    # ISO 8601 UTC datetime, e.g. "2026-04-01T14:00:00+00:00"
    scheduled_for: str
    status: OccurrenceStatus = "scheduled"
    overrides: OccurrenceOverrides | None = None
    # Optional FK to a ContentPacket document (added in later phase)
    content_packet_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Sequence index within the series (0-based), used for ordering
    sequence_index: int | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "occurrence_id": self.occurrence_id,
            "series_id": self.series_id,
            "workspace_id": self.workspace_id,
            "scheduled_for": self.scheduled_for,
            "status": self.status,
            "overrides": self.overrides.to_dict() if self.overrides else None,
            "content_packet_id": self.content_packet_id,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
            "sequence_index": self.sequence_index,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Occurrence:
        raw_overrides = data.get("overrides")
        return cls(
            occurrence_id=data["occurrence_id"],
            series_id=data["series_id"],
            workspace_id=data["workspace_id"],
            scheduled_for=data["scheduled_for"],
            status=data.get("status", "scheduled"),
            overrides=OccurrenceOverrides.from_dict(raw_overrides) if raw_overrides else None,
            content_packet_id=data.get("content_packet_id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            sequence_index=data.get("sequence_index"),
        )


# ---------------------------------------------------------------------------
# CheckIn
# ---------------------------------------------------------------------------

@dataclass
class CheckIn:
    """Records a participant's attendance or response to an Occurrence.

    Maps to the Firestore ``check_ins`` collection.
    """

    check_in_id: str
    occurrence_id: str
    series_id: str
    workspace_id: str
    user_id: str
    status: CheckInStatus = "pending"
    checked_in_at: datetime | None = None
    note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "check_in_id": self.check_in_id,
            "occurrence_id": self.occurrence_id,
            "series_id": self.series_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "status": self.status,
            "checked_in_at": self.checked_in_at,
            "note": self.note,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CheckIn:
        return cls(
            check_in_id=data["check_in_id"],
            occurrence_id=data["occurrence_id"],
            series_id=data["series_id"],
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            status=data.get("status", "pending"),
            checked_in_at=data.get("checked_in_at"),
            note=data.get("note"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# NotificationRule
# ---------------------------------------------------------------------------

@dataclass
class NotificationRule:
    """Per-workspace rule controlling when and how notifications are sent.

    Maps to the Firestore ``notification_rules`` collection.
    """

    rule_id: str
    workspace_id: str
    series_id: str | None  # None means workspace-level default
    channel: NotificationChannel
    # Minutes before the occurrence to send the reminder (e.g. 60 = 1 hour before)
    remind_before_minutes: int
    enabled: bool = True
    # Optional: restrict delivery to specific member roles
    target_roles: list[MemberRole] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "rule_id": self.rule_id,
            "workspace_id": self.workspace_id,
            "series_id": self.series_id,
            "channel": self.channel,
            "remind_before_minutes": self.remind_before_minutes,
            "enabled": self.enabled,
            "target_roles": self.target_roles,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NotificationRule:
        return cls(
            rule_id=data["rule_id"],
            workspace_id=data["workspace_id"],
            series_id=data.get("series_id"),
            channel=data["channel"],
            remind_before_minutes=int(data["remind_before_minutes"]),
            enabled=bool(data.get("enabled", True)),
            target_roles=list(data.get("target_roles", [])),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# DeliveryLog
# ---------------------------------------------------------------------------

@dataclass
class DeliveryLog:
    """Immutable audit record for each notification delivery attempt.

    Maps to the Firestore ``delivery_logs`` collection.
    """

    log_id: str
    rule_id: str
    occurrence_id: str
    workspace_id: str
    recipient_uid: str
    channel: NotificationChannel
    status: DeliveryStatus
    sent_at: datetime | None = None
    error: str | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "log_id": self.log_id,
            "rule_id": self.rule_id,
            "occurrence_id": self.occurrence_id,
            "workspace_id": self.workspace_id,
            "recipient_uid": self.recipient_uid,
            "channel": self.channel,
            "status": self.status,
            "sent_at": self.sent_at,
            "error": self.error,
            "created_at": self.created_at or now,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeliveryLog:
        return cls(
            log_id=data["log_id"],
            rule_id=data["rule_id"],
            occurrence_id=data["occurrence_id"],
            workspace_id=data["workspace_id"],
            recipient_uid=data["recipient_uid"],
            channel=data["channel"],
            status=data["status"],
            sent_at=data.get("sent_at"),
            error=data.get("error"),
            created_at=data.get("created_at"),
        )
