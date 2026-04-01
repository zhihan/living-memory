"""Domain models for the pivot to a recurring-schedule platform.

New vocabulary:
- Room       (replaces Workspace/Page)
- Series     (a recurring schedule)
- Occurrence (a single instance of a Series)
- CheckIn    (participant attendance/confirmation)
- NotificationRule  (per-room delivery preferences)
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

RoomType = Literal["personal", "shared", "study"]
SeriesKind = Literal["reminder", "meeting", "study_assignment"]
SeriesStatus = Literal["active", "paused", "archived"]
OccurrenceStatus = Literal["scheduled", "cancelled", "completed", "rescheduled"]
CheckInStatus = Literal["pending", "confirmed", "declined", "missed"]
MemberRole = Literal["organizer", "participant", "teacher", "assistant", "student"]
NotificationChannel = Literal["email", "in_app", "telegram", "calendar"]
DeliveryStatus = Literal["pending", "sent", "failed", "skipped"]
BotMode = Literal["read_only", "read_write"]


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

@dataclass
class Room:
    """Top-level container for a group of related recurring schedules.

    Maps to the Firestore ``workspaces`` collection.
    """

    room_id: str
    title: str
    type: RoomType
    timezone: str
    owner_uids: list[str]
    # uid -> MemberRole; owners are also listed here with role "organizer"
    member_roles: dict[str, MemberRole] = field(default_factory=dict)
    # uid -> lightweight display metadata for room member lists
    member_profiles: dict[str, dict[str, str | None]] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    description: str | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "room_id": self.room_id,
            "title": self.title,
            "type": self.type,
            "timezone": self.timezone,
            "owner_uids": self.owner_uids,
            "member_roles": self.member_roles,
            "member_profiles": self.member_profiles,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Room:
        return cls(
            room_id=data.get("room_id") or data.get("workspace_id", ""),
            title=data["title"],
            type=data["type"],
            timezone=data.get("timezone", "UTC"),
            owner_uids=list(data.get("owner_uids", [])),
            member_roles=dict(data.get("member_roles", {})),
            member_profiles=dict(data.get("member_profiles", {})),
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
      - ``"daily"``     -- every day
      - ``"weekly"``    -- every week on ``weekdays``
      - ``"weekdays"``  -- Monday-Friday
      - ``"custom"``    -- specific weekday list (same as weekly but explicit)
      - ``"once"``      -- no recurrence (single-shot)

    ``weekdays`` is a list of ISO weekday integers (1=Monday ... 7=Sunday).
    For ``daily`` and ``weekdays`` frequency, ``weekdays`` is ignored.

    ``interval`` is how many units to skip between occurrences (default 1).
    For example ``interval=2`` with ``frequency="weekly"`` means every two weeks.

    ``until`` is an optional UTC datetime after which no new occurrences
    should be generated.

    ``count`` is an optional cap on the total number of occurrences to generate.
    """

    frequency: Literal["daily", "weekly", "weekdays", "custom", "once"]
    weekdays: list[int] = field(default_factory=list)  # 1=Mon ... 7=Sun
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
    """A recurring schedule owned by a Room.

    Maps to the Firestore ``series`` collection.
    """

    series_id: str
    room_id: str
    kind: SeriesKind
    title: str
    schedule_rule: ScheduleRule
    # Wall-clock time of day: "HH:MM" in the room's timezone
    default_time: str | None = None
    default_duration_minutes: int | None = None
    default_location: str | None = None
    default_online_link: str | None = None
    # "none" = no location; "fixed" = same location every time; "per_occurrence" = set per meeting
    location_type: Literal["none", "fixed", "per_occurrence"] = "fixed"
    # Ordered list of locations for rotation mode
    location_rotation: list[str] | None = None
    status: SeriesStatus = "active"
    # ISO weekdays (1=Mon ... 7=Sun) on which check-in is enabled; empty/None = no check-ins
    # DEPRECATED: kept for reading old data; use enable_done instead
    check_in_weekdays: list[int] | None = None
    # Simple boolean: when True, all generated occurrences get enable_check_in=True
    enable_done: bool = False
    # Host rotation fields
    rotation_mode: str = "none"  # "none", "manual", "host_only", "host_and_location"
    host_rotation: list[str] | None = None  # List of host labels
    host_addresses: dict[str, str] | None = None  # Maps host names to addresses
    created_at: datetime | None = None
    updated_at: datetime | None = None
    description: str | None = None
    # UID of the user who created this series
    created_by: str | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "series_id": self.series_id,
            "room_id": self.room_id,
            "kind": self.kind,
            "title": self.title,
            "schedule_rule": self.schedule_rule.to_dict(),
            "default_time": self.default_time,
            "default_duration_minutes": self.default_duration_minutes,
            "default_location": self.default_location,
            "default_online_link": self.default_online_link,
            "location_type": self.location_type,
            "location_rotation": self.location_rotation,
            "status": self.status,
            "check_in_weekdays": self.check_in_weekdays,
            "enable_done": self.enable_done,
            "rotation_mode": self.rotation_mode,
            "host_rotation": self.host_rotation,
            "host_addresses": self.host_addresses,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
            "description": self.description,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Series:
        # Backward compat: if doc has non-empty check_in_weekdays but no
        # explicit enable_done, treat it as enable_done=True.
        check_in_weekdays = data.get("check_in_weekdays")
        if "enable_done" in data:
            enable_done = bool(data["enable_done"])
        else:
            enable_done = bool(check_in_weekdays)
        return cls(
            series_id=data["series_id"],
            room_id=data.get("room_id") or data.get("workspace_id", ""),
            kind=data["kind"],
            title=data["title"],
            schedule_rule=ScheduleRule.from_dict(data["schedule_rule"]),
            default_time=data.get("default_time"),
            default_duration_minutes=data.get("default_duration_minutes"),
            default_location=data.get("default_location"),
            default_online_link=data.get("default_online_link"),
            location_type="fixed" if data.get("location_type") == "rotation" else data.get("location_type", "fixed"),
            location_rotation=data.get("location_rotation"),
            status=data.get("status", "active"),
            check_in_weekdays=check_in_weekdays,
            enable_done=enable_done,
            rotation_mode=data.get("rotation_mode", "none"),
            host_rotation=data.get("host_rotation"),
            host_addresses=data.get("host_addresses"),
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
    notes: str | None = None

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "duration_minutes": self.duration_minutes,
            "location": self.location,
            "online_link": self.online_link,
            "title": self.title,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OccurrenceOverrides:
        return cls(
            time=data.get("time"),
            duration_minutes=data.get("duration_minutes"),
            location=data.get("location"),
            online_link=data.get("online_link"),
            title=data.get("title"),
            notes=data.get("notes"),
        )


@dataclass
class Occurrence:
    """A single scheduled instance of a Series.

    Maps to the Firestore ``occurrences`` collection.
    ``scheduled_for`` is an ISO 8601 UTC datetime string representing the
    start of this occurrence.  Effective wall-clock time is determined by
    either ``overrides.time`` or ``Series.default_time`` plus the room
    timezone.
    """

    occurrence_id: str
    series_id: str
    room_id: str
    # ISO 8601 UTC datetime, e.g. "2026-04-01T14:00:00+00:00"
    scheduled_for: str
    status: OccurrenceStatus = "scheduled"
    # Per-occurrence location (always present; set from series default or per-occurrence)
    location: str | None = None
    # Host for this occurrence (from rotation or manual assignment)
    host: str | None = None
    overrides: OccurrenceOverrides | None = None
    # Optional FK to a ContentPacket document (added in later phase)
    content_packet_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Sequence index within the series (0-based), used for ordering
    sequence_index: int | None = None
    # Whether participants can check in on this occurrence
    enable_check_in: bool = False

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "occurrence_id": self.occurrence_id,
            "series_id": self.series_id,
            "room_id": self.room_id,
            "scheduled_for": self.scheduled_for,
            "status": self.status,
            "location": self.location,
            "host": self.host,
            "overrides": self.overrides.to_dict() if self.overrides else None,
            "content_packet_id": self.content_packet_id,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
            "sequence_index": self.sequence_index,
            "enable_check_in": self.enable_check_in,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Occurrence:
        raw_overrides = data.get("overrides")
        return cls(
            occurrence_id=data["occurrence_id"],
            series_id=data["series_id"],
            room_id=data.get("room_id") or data.get("workspace_id", ""),
            scheduled_for=data["scheduled_for"],
            status=data.get("status", "scheduled"),
            location=data.get("location"),
            host=data.get("host"),
            overrides=OccurrenceOverrides.from_dict(raw_overrides) if raw_overrides else None,
            content_packet_id=data.get("content_packet_id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            sequence_index=data.get("sequence_index"),
            enable_check_in=bool(data.get("enable_check_in", False)),
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
    room_id: str
    user_id: str
    display_name: str | None = None
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
            "room_id": self.room_id,
            "user_id": self.user_id,
            "display_name": self.display_name,
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
            room_id=data.get("room_id") or data.get("workspace_id", ""),
            user_id=data["user_id"],
            display_name=data.get("display_name"),
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
    """Per-room rule controlling when and how notifications are sent.

    Maps to the Firestore ``notification_rules`` collection.
    """

    rule_id: str
    room_id: str
    series_id: str | None  # None means room-level default
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
            "room_id": self.room_id,
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
            room_id=data.get("room_id") or data.get("workspace_id", ""),
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
    room_id: str
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
            "room_id": self.room_id,
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
            room_id=data.get("room_id") or data.get("workspace_id", ""),
            recipient_uid=data["recipient_uid"],
            channel=data["channel"],
            status=data["status"],
            sent_at=data.get("sent_at"),
            error=data.get("error"),
            created_at=data.get("created_at"),
        )


# ---------------------------------------------------------------------------
# TelegramBotConfig
# ---------------------------------------------------------------------------

@dataclass
class TelegramBotConfig:
    """Configuration for a room's dedicated Telegram bot.

    Maps to the Firestore ``telegram_bots`` collection.
    """

    bot_id: str              # Telegram bot user ID (from getMe) — doc ID
    room_id: str             # FK to workspaces collection
    bot_token: str           # encrypted at rest
    bot_username: str        # e.g. "MyMeetingBot"
    webhook_secret: str      # auto-generated per bot
    mode: BotMode = "read_only"
    created_by: str = ""     # UID of organizer who configured it
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "bot_id": self.bot_id,
            "room_id": self.room_id,
            "bot_token": self.bot_token,
            "bot_username": self.bot_username,
            "webhook_secret": self.webhook_secret,
            "mode": self.mode,
            "created_by": self.created_by,
            "active": self.active,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TelegramBotConfig:
        return cls(
            bot_id=data["bot_id"],
            room_id=data["room_id"],
            bot_token=data["bot_token"],
            bot_username=data["bot_username"],
            webhook_secret=data["webhook_secret"],
            mode=data.get("mode", "read_only"),
            created_by=data.get("created_by", ""),
            active=bool(data.get("active", True)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# TelegramUserLink
# ---------------------------------------------------------------------------

@dataclass
class TelegramUserLink:
    """Maps a Telegram user to an app user.

    Maps to the Firestore ``telegram_links`` collection.
    """

    telegram_user_id: str  # doc ID
    app_uid: str           # Firebase UID
    display_name: str
    linked_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "telegram_user_id": self.telegram_user_id,
            "app_uid": self.app_uid,
            "display_name": self.display_name,
            "linked_at": self.linked_at or _utcnow(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> TelegramUserLink:
        return cls(
            telegram_user_id=data["telegram_user_id"],
            app_uid=data["app_uid"],
            display_name=data["display_name"],
            linked_at=data.get("linked_at"),
        )


# ---------------------------------------------------------------------------
# ChatSession / ChatTurn
# ---------------------------------------------------------------------------

@dataclass
class ChatTurn:
    """A single turn in a Telegram chat session."""

    role: str  # "user" or "assistant"
    text: str
    timestamp: datetime | None = None
    action_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp or _utcnow(),
            "action_id": self.action_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ChatTurn:
        return cls(
            role=data["role"],
            text=data["text"],
            timestamp=data.get("timestamp"),
            action_id=data.get("action_id"),
        )


@dataclass
class ChatSession:
    """Telegram chat session with conversation history.

    Maps to the Firestore ``chat_sessions`` collection.
    Session key: (room_id, telegram_chat_id).
    """

    session_id: str
    room_id: str
    telegram_chat_id: str
    app_uid: str
    turns: list[ChatTurn] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        now = _utcnow()
        return {
            "session_id": self.session_id,
            "room_id": self.room_id,
            "telegram_chat_id": self.telegram_chat_id,
            "app_uid": self.app_uid,
            "turns": [t.to_dict() for t in self.turns],
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ChatSession:
        return cls(
            session_id=data["session_id"],
            room_id=data["room_id"],
            telegram_chat_id=data["telegram_chat_id"],
            app_uid=data["app_uid"],
            turns=[ChatTurn.from_dict(t) for t in data.get("turns", [])],
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
