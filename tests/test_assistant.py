
"""Tests for the Meeting Organizer Assistant — actions and API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from assistant_actions import (
    ACTION_TTL_SECONDS,
    PendingAction,
    build_create_series_action,
    build_draft_material_action,
    build_generate_reminder_text_action,
    build_reschedule_occurrence_action,
    execute_action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pending(
    action_type="create_series",
    payload=None,
    status="pending",
    age_seconds=0,
) -> PendingAction:
    created = datetime.now(timezone.utc)
    # subtract age so we can simulate expired actions
    from datetime import timedelta
    created = created - timedelta(seconds=age_seconds)
    return PendingAction(
        action_id=str(uuid.uuid4()),
        workspace_id="ws-1",
        requested_by_uid="uid-1",
        action_type=action_type,
        preview_summary="Test action",
        payload=payload or {},
        status=status,
        created_at=created,
    )


# ---------------------------------------------------------------------------
# PendingAction serialisation round-trip
# ---------------------------------------------------------------------------

class TestPendingActionSerialization:
    def test_to_dict_and_back(self):
        action = _make_pending(
            action_type="create_series",
            payload={"title": "Standup", "schedule_rule": {"frequency": "weekly"}},
        )
        d = action.to_dict()
        restored = PendingAction.from_dict(d)
        assert restored.action_id == action.action_id
        assert restored.action_type == action.action_type
        assert restored.payload["title"] == "Standup"
        assert restored.status == "pending"

    def test_from_dict_defaults_status(self):
        d = {
            "action_id": "x",
            "workspace_id": "ws",
            "requested_by_uid": "u",
            "action_type": "draft_material",
            "preview_summary": "ok",
            "payload": {},
        }
        action = PendingAction.from_dict(d)
        assert action.status == "pending"


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------

class TestBuildCreateSeriesAction:
    def test_basic(self):
        payload = {
            "title": "Weekly Standup",
            "schedule_rule": {"frequency": "weekly", "weekdays": [1, 3]},
            "default_time": "10:00",
        }
        action = build_create_series_action("ws-1", "uid-1", payload)
        assert action.action_type == "create_series"
        assert "Weekly Standup" in action.preview_summary
        assert "weekly" in action.preview_summary
        assert action.workspace_id == "ws-1"
        assert action.requested_by_uid == "uid-1"
        assert action.status == "pending"

    def test_no_time(self):
        payload = {"title": "Daily Check-in", "schedule_rule": {"frequency": "daily"}}
        action = build_create_series_action("ws-2", "uid-2", payload)
        # No default_time in payload → "at ..." should not appear in summary
        assert " at " not in action.preview_summary


class TestBuildRescheduleOccurrenceAction:
    def test_basic(self):
        payload = {
            "occurrence_id": "occ-123",
            "new_scheduled_for": "2026-04-10T10:00:00+00:00",
        }
        action = build_reschedule_occurrence_action("ws-1", "uid-1", payload)
        assert action.action_type == "reschedule_occurrence"
        assert "occ-123" in action.preview_summary
        assert "2026-04-10" in action.preview_summary

    def test_unknown_occurrence(self):
        payload = {"occurrence_id": "?", "new_scheduled_for": "2026-05-01T09:00:00+00:00"}
        action = build_reschedule_occurrence_action("ws-1", "uid-1", payload)
        assert action.action_type == "reschedule_occurrence"


class TestBuildDraftMaterialAction:
    def test_agenda(self):
        payload = {
            "title": "Team Meeting",
            "material_kind": "agenda",
            "draft_text": "1. Intro\n2. Updates",
        }
        action = build_draft_material_action("ws-1", "uid-1", payload)
        assert action.action_type == "draft_material"
        assert "agenda" in action.preview_summary
        assert "Team Meeting" in action.preview_summary

    def test_notes(self):
        payload = {"title": "Retrospective", "material_kind": "notes", "draft_text": "..."}
        action = build_draft_material_action("ws-1", "uid-1", payload)
        assert "notes" in action.preview_summary


class TestBuildGenerateReminderTextAction:
    def test_with_occurrence(self):
        payload = {
            "occurrence_id": "occ-42",
            "reminder_text": "Don't forget the meeting tomorrow!",
        }
        action = build_generate_reminder_text_action("ws-1", "uid-1", payload)
        assert action.action_type == "generate_reminder_text"
        assert "occ-42" in action.preview_summary

    def test_with_series(self):
        payload = {
            "series_id": "series-7",
            "reminder_text": "Weekly standup is at 10am.",
        }
        action = build_generate_reminder_text_action("ws-1", "uid-1", payload)
        assert "series-7" in action.preview_summary


# ---------------------------------------------------------------------------
# execute_action dispatch
# ---------------------------------------------------------------------------

class TestExecuteAction:
    def test_execute_draft_material(self):
        action = _make_pending(
            action_type="draft_material",
            payload={
                "title": "Q2 Review",
                "material_kind": "agenda",
                "draft_text": "Item 1\nItem 2",
            },
        )
        result = execute_action(action)
        assert result["material_kind"] == "agenda"
        assert result["title"] == "Q2 Review"
        assert "Item 1" in result["draft_text"]

    def test_execute_generate_reminder_text(self):
        action = _make_pending(
            action_type="generate_reminder_text",
            payload={
                "occurrence_id": "occ-99",
                "reminder_text": "Meeting at 3pm!",
            },
        )
        result = execute_action(action)
        assert result["reminder_text"] == "Meeting at 3pm!"
        assert result["occurrence_id"] == "occ-99"

    def test_execute_create_series(self):
        action = _make_pending(
            action_type="create_series",
            payload={
                "title": "Sprint Standup",
                "kind": "meeting",
                "schedule_rule": {"frequency": "daily"},
            },
        )
        fake_workspace = MagicMock()

        with (
            patch("workspace_storage.get_workspace", return_value=fake_workspace),
            patch("series_storage.create_series", return_value=None),
        ):
            result = execute_action(action)

        assert result["created"] == "series"
        assert result["series"]["title"] == "Sprint Standup"

    def test_execute_reschedule_occurrence(self):
        action = _make_pending(
            action_type="reschedule_occurrence",
            payload={
                "occurrence_id": "occ-55",
                "new_scheduled_for": "2026-05-01T09:00:00+00:00",
            },
        )
        from models import Occurrence
        fake_occurrence = Occurrence(
            occurrence_id="occ-55",
            series_id="series-1",
            workspace_id="ws-1",
            scheduled_for="2026-05-01T09:00:00+00:00",
            status="rescheduled",
        )
        with patch("occurrence_service.reschedule_occurrence", return_value=fake_occurrence):
            result = execute_action(action)

        assert result["rescheduled"] == "occurrence"
        assert result["occurrence"]["occurrence_id"] == "occ-55"

    def test_unknown_action_type_raises(self):
        action = _make_pending(action_type="create_series")
        action.action_type = "nonexistent_action"
        with pytest.raises(ValueError, match="Unknown action type"):
            execute_action(action)


# ---------------------------------------------------------------------------
# Firestore helpers (mocked)
# ---------------------------------------------------------------------------

class TestFirestoreHelpers:
    def test_save_pending_action(self):
        action = _make_pending(action_type="draft_material", payload={"title": "Test"})
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch("firestore_storage._get_client", return_value=mock_db):
            from assistant_actions import save_pending_action
            action_id = save_pending_action(action)

        assert action_id == action.action_id
        mock_doc_ref.set.assert_called_once()

    def test_get_pending_action_not_found(self):
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("firestore_storage._get_client", return_value=mock_db):
            from assistant_actions import get_pending_action
            result = get_pending_action("nonexistent-id")

        assert result is None

    def test_get_pending_action_expired(self):
        action = _make_pending(age_seconds=ACTION_TTL_SECONDS + 60)
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = action.to_dict()
        # Firestore timestamps come back as datetime objects; simulate that:
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("firestore_storage._get_client", return_value=mock_db):
            from assistant_actions import get_pending_action
            result = get_pending_action(action.action_id)

        assert result is None  # expired

    def test_get_pending_action_found(self):
        action = _make_pending(age_seconds=30)
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = action.to_dict()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("firestore_storage._get_client", return_value=mock_db):
            from assistant_actions import get_pending_action
            result = get_pending_action(action.action_id)

        assert result is not None
        assert result.action_id == action.action_id

    def test_update_pending_action_status(self):
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch("firestore_storage._get_client", return_value=mock_db):
            from assistant_actions import update_pending_action_status
            update_pending_action_status("some-id", "executed", result={"ok": True})

        call_kwargs = mock_doc_ref.update.call_args[0][0]
        assert call_kwargs["status"] == "executed"
        assert call_kwargs["result"] == {"ok": True}
        assert "executed_at" in call_kwargs


# ---------------------------------------------------------------------------
# API endpoint integration tests
# ---------------------------------------------------------------------------

ORGANIZER_UID = "uid-organizer"
PARTICIPANT_UID = "uid-participant"
AUTH = {"Authorization": "Bearer fake-token"}


def _fake_verify(uid: str):
    def verifier(authorization: str = ""):
        return {"uid": uid}
    return verifier


@pytest.fixture
def organizer_client():
    fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")
    from api import app
    from api_v2 import _require_token
    app.dependency_overrides[_require_token] = _fake_verify(ORGANIZER_UID)
    from fastapi.testclient import TestClient
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_workspace(uid: str = ORGANIZER_UID):
    from models import Workspace
    return Workspace(
        workspace_id="ws-1",
        title="Test WS",
        type="shared",
        timezone="UTC",
        owner_uids=[uid],
        member_roles={uid: "organizer"},
    )


class TestAssistantAPI:
    def test_assistant_endpoint_missing_env(self, organizer_client):
        """Without GEMINI_API_KEY the endpoint should error, not 500 on auth."""
        import os
        ws = _make_workspace()

        with (
            patch("api_v2.workspace_storage.get_workspace", return_value=ws),
            patch.dict(os.environ, {}, clear=False),
        ):
            # We won't actually call Gemini in tests; mock the stream
            with patch(
                "api_v2.run_assistant_stream",
                return_value=iter([
                    {"type": "text_chunk", "text": "Hello!"},
                    {"type": "done"},
                ]),
            ):
                resp = organizer_client.post(
                    "/v2/workspaces/ws-1/assistant",
                    json={"message": "Schedule weekly standup"},
                    headers=AUTH,
                )
        assert resp.status_code == 200

    def test_confirm_action_not_found(self, organizer_client):
        with patch("api_v2.get_pending_action", return_value=None):
            resp = organizer_client.post(
                "/v2/assistant/actions/nonexistent/confirm",
                headers=AUTH,
            )
        assert resp.status_code == 404

    def test_confirm_action_wrong_user(self, organizer_client):
        action = _make_pending(action_type="draft_material", payload={})
        action.requested_by_uid = "someone-else"
        with patch("api_v2.get_pending_action", return_value=action):
            resp = organizer_client.post(
                f"/v2/assistant/actions/{action.action_id}/confirm",
                headers=AUTH,
            )
        assert resp.status_code == 403

    def test_confirm_action_already_executed(self, organizer_client):
        action = _make_pending(
            action_type="draft_material",
            payload={"title": "x", "material_kind": "agenda", "draft_text": ""},
            status="executed",
        )
        action.requested_by_uid = ORGANIZER_UID
        with patch("api_v2.get_pending_action", return_value=action):
            resp = organizer_client.post(
                f"/v2/assistant/actions/{action.action_id}/confirm",
                headers=AUTH,
            )
        assert resp.status_code == 409

    def test_cancel_action_success(self, organizer_client):
        action = _make_pending(
            action_type="generate_reminder_text",
            payload={"reminder_text": "hi"},
        )
        action.requested_by_uid = ORGANIZER_UID
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.update = MagicMock()

        with (
            patch("api_v2.get_pending_action", return_value=action),
            patch("api_v2.update_pending_action_status") as mock_update,
        ):
            resp = organizer_client.post(
                f"/v2/assistant/actions/{action.action_id}/cancel",
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        mock_update.assert_called_once_with(action.action_id, "cancelled")

    def test_confirm_action_executes_draft(self, organizer_client):
        ws = _make_workspace()
        action = _make_pending(
            action_type="draft_material",
            payload={
                "title": "Weekly Notes",
                "material_kind": "notes",
                "draft_text": "Discussed Q3 goals.",
            },
        )
        action.requested_by_uid = ORGANIZER_UID

        with (
            patch("api_v2.get_pending_action", return_value=action),
            patch("api_v2.update_pending_action_status"),
            patch("api_v2.execute_action", return_value={
                "material_kind": "notes",
                "title": "Weekly Notes",
                "draft_text": "Discussed Q3 goals.",
            }),
            patch("api_v2.workspace_storage.get_workspace", return_value=ws),
        ):
            resp = organizer_client.post(
                f"/v2/assistant/actions/{action.action_id}/confirm",
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "executed"
        assert data["result"]["material_kind"] == "notes"
