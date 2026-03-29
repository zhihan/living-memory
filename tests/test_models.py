"""Tests for Phase 1 domain models (models.py).

These tests exercise serialization round-trips and validation logic
without requiring a Firestore connection.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from models import (
    CheckIn,
    DeliveryLog,
    NotificationRule,
    Occurrence,
    OccurrenceOverrides,
    ScheduleRule,
    Series,
    Workspace,
)


# ---------------------------------------------------------------------------
# ScheduleRule
# ---------------------------------------------------------------------------

class TestScheduleRule:
    def test_roundtrip_weekly(self):
        rule = ScheduleRule(frequency="weekly", weekdays=[1, 3, 5], interval=2)
        restored = ScheduleRule.from_dict(rule.to_dict())
        assert restored.frequency == "weekly"
        assert restored.weekdays == [1, 3, 5]
        assert restored.interval == 2
        assert restored.until is None
        assert restored.count is None

    def test_roundtrip_with_until(self):
        until = datetime(2026, 12, 31, 23, 59, 0, tzinfo=timezone.utc)
        rule = ScheduleRule(frequency="daily", until=until)
        restored = ScheduleRule.from_dict(rule.to_dict())
        assert restored.until is not None
        assert restored.until.year == 2026

    def test_roundtrip_once(self):
        rule = ScheduleRule(frequency="once")
        restored = ScheduleRule.from_dict(rule.to_dict())
        assert restored.frequency == "once"
        assert restored.weekdays == []

    def test_default_interval(self):
        rule = ScheduleRule(frequency="daily")
        assert rule.interval == 1
        restored = ScheduleRule.from_dict(rule.to_dict())
        assert restored.interval == 1


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

class TestWorkspace:
    def _make(self, **kwargs) -> Workspace:
        defaults = dict(
            workspace_id="ws-1",
            title="Team Standups",
            type="shared",
            timezone="America/New_York",
            owner_uids=["uid-alice"],
        )
        defaults.update(kwargs)
        return Workspace(**defaults)

    def test_roundtrip(self):
        ws = self._make()
        restored = Workspace.from_dict(ws.to_dict())
        assert restored.workspace_id == "ws-1"
        assert restored.title == "Team Standups"
        assert restored.type == "shared"
        assert restored.timezone == "America/New_York"
        assert restored.owner_uids == ["uid-alice"]

    def test_member_roles_roundtrip(self):
        ws = self._make(member_roles={"uid-alice": "organizer", "uid-bob": "participant"})
        restored = Workspace.from_dict(ws.to_dict())
        assert restored.member_roles["uid-alice"] == "organizer"
        assert restored.member_roles["uid-bob"] == "participant"

    def test_default_timezone(self):
        ws = self._make()
        d = ws.to_dict()
        del d["timezone"]
        # Simulate loading a doc without timezone
        restored = Workspace.from_dict({**d, "workspace_id": "ws-1"})
        assert restored.timezone == "UTC"

    def test_description_optional(self):
        ws = self._make()
        assert ws.description is None
        restored = Workspace.from_dict(ws.to_dict())
        assert restored.description is None


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

class TestSeries:
    def _make(self, **kwargs) -> Series:
        defaults = dict(
            series_id="series-1",
            workspace_id="ws-1",
            kind="meeting",
            title="Weekly Standup",
            schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
            default_time="09:00",
            created_by="uid-alice",
        )
        defaults.update(kwargs)
        return Series(**defaults)

    def test_roundtrip(self):
        s = self._make()
        restored = Series.from_dict(s.to_dict())
        assert restored.series_id == "series-1"
        assert restored.kind == "meeting"
        assert restored.schedule_rule.frequency == "weekly"
        assert restored.schedule_rule.weekdays == [1]
        assert restored.default_time == "09:00"
        assert restored.status == "active"

    def test_optional_fields(self):
        s = self._make()
        assert s.default_location is None
        assert s.default_online_link is None
        assert s.default_duration_minutes is None
        restored = Series.from_dict(s.to_dict())
        assert restored.default_location is None

    def test_status_default(self):
        s = self._make()
        d = s.to_dict()
        del d["status"]
        restored = Series.from_dict(d)
        assert restored.status == "active"


# ---------------------------------------------------------------------------
# Occurrence
# ---------------------------------------------------------------------------

class TestOccurrence:
    def _make(self, **kwargs) -> Occurrence:
        defaults = dict(
            occurrence_id="occ-1",
            series_id="series-1",
            workspace_id="ws-1",
            scheduled_for="2026-04-01T14:00:00+00:00",
        )
        defaults.update(kwargs)
        return Occurrence(**defaults)

    def test_roundtrip(self):
        occ = self._make()
        restored = Occurrence.from_dict(occ.to_dict())
        assert restored.occurrence_id == "occ-1"
        assert restored.scheduled_for == "2026-04-01T14:00:00+00:00"
        assert restored.status == "scheduled"
        assert restored.overrides is None

    def test_with_overrides(self):
        overrides = OccurrenceOverrides(
            time="10:00",
            location="Room B",
            online_link="https://zoom.us/j/123",
        )
        occ = self._make(overrides=overrides)
        restored = Occurrence.from_dict(occ.to_dict())
        assert restored.overrides is not None
        assert restored.overrides.time == "10:00"
        assert restored.overrides.location == "Room B"
        assert restored.overrides.online_link == "https://zoom.us/j/123"

    def test_status_values(self):
        for status in ("scheduled", "cancelled", "completed", "rescheduled"):
            occ = self._make(status=status)
            restored = Occurrence.from_dict(occ.to_dict())
            assert restored.status == status

    def test_status_default(self):
        occ = self._make()
        d = occ.to_dict()
        del d["status"]
        restored = Occurrence.from_dict(d)
        assert restored.status == "scheduled"

    def test_sequence_index(self):
        occ = self._make(sequence_index=5)
        restored = Occurrence.from_dict(occ.to_dict())
        assert restored.sequence_index == 5


# ---------------------------------------------------------------------------
# CheckIn
# ---------------------------------------------------------------------------

class TestCheckIn:
    def _make(self, **kwargs) -> CheckIn:
        defaults = dict(
            check_in_id="ci-1",
            occurrence_id="occ-1",
            series_id="series-1",
            workspace_id="ws-1",
            user_id="uid-bob",
        )
        defaults.update(kwargs)
        return CheckIn(**defaults)

    def test_roundtrip(self):
        ci = self._make()
        restored = CheckIn.from_dict(ci.to_dict())
        assert restored.check_in_id == "ci-1"
        assert restored.user_id == "uid-bob"
        assert restored.status == "pending"

    def test_confirmed_with_timestamp(self):
        now = datetime(2026, 4, 1, 14, 5, 0, tzinfo=timezone.utc)
        ci = self._make(status="confirmed", checked_in_at=now)
        restored = CheckIn.from_dict(ci.to_dict())
        assert restored.status == "confirmed"
        assert restored.checked_in_at == now

    def test_note_optional(self):
        ci = self._make(note="Running 5 min late")
        restored = CheckIn.from_dict(ci.to_dict())
        assert restored.note == "Running 5 min late"


# ---------------------------------------------------------------------------
# NotificationRule
# ---------------------------------------------------------------------------

class TestNotificationRule:
    def test_roundtrip(self):
        rule = NotificationRule(
            rule_id="rule-1",
            workspace_id="ws-1",
            series_id="series-1",
            channel="email",
            remind_before_minutes=60,
            target_roles=["participant", "organizer"],
        )
        restored = NotificationRule.from_dict(rule.to_dict())
        assert restored.rule_id == "rule-1"
        assert restored.channel == "email"
        assert restored.remind_before_minutes == 60
        assert restored.target_roles == ["participant", "organizer"]
        assert restored.enabled is True

    def test_workspace_level_rule(self):
        rule = NotificationRule(
            rule_id="rule-2",
            workspace_id="ws-1",
            series_id=None,
            channel="in_app",
            remind_before_minutes=30,
        )
        restored = NotificationRule.from_dict(rule.to_dict())
        assert restored.series_id is None


# ---------------------------------------------------------------------------
# DeliveryLog
# ---------------------------------------------------------------------------

class TestDeliveryLog:
    def test_roundtrip_sent(self):
        sent_at = datetime(2026, 4, 1, 13, 0, 0, tzinfo=timezone.utc)
        log = DeliveryLog(
            log_id="log-1",
            rule_id="rule-1",
            occurrence_id="occ-1",
            workspace_id="ws-1",
            recipient_uid="uid-bob",
            channel="email",
            status="sent",
            sent_at=sent_at,
        )
        restored = DeliveryLog.from_dict(log.to_dict())
        assert restored.log_id == "log-1"
        assert restored.status == "sent"
        assert restored.sent_at == sent_at
        assert restored.error is None

    def test_roundtrip_failed(self):
        log = DeliveryLog(
            log_id="log-2",
            rule_id="rule-1",
            occurrence_id="occ-1",
            workspace_id="ws-1",
            recipient_uid="uid-bob",
            channel="email",
            status="failed",
            error="SMTP connection refused",
        )
        restored = DeliveryLog.from_dict(log.to_dict())
        assert restored.status == "failed"
        assert restored.error == "SMTP connection refused"
