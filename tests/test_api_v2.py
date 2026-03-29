"""Integration tests for the v2 API (api_v2.py).

Uses FastAPI TestClient with Firebase auth dependency overridden.
Firestore storage is mocked per test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from models import (
    CheckIn,
    Occurrence,
    OccurrenceOverrides,
    ScheduleRule,
    Series,
    Workspace,
)

ORGANIZER_UID = "uid-organizer"
PARTICIPANT_UID = "uid-participant"
OUTSIDER_UID = "uid-outsider"
AUTH = {"Authorization": "Bearer fake-token"}


def _utcnow():
    return datetime.now(timezone.utc)


def _fake_verify(uid: str):
    def verifier(authorization: str = ""):
        return {"uid": uid}
    return verifier


@pytest.fixture
def organizer_client():
    from api import app
    from api_v2 import _require_token
    app.dependency_overrides[_require_token] = _fake_verify(ORGANIZER_UID)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def participant_client():
    from api import app
    from api_v2 import _require_token
    app.dependency_overrides[_require_token] = _fake_verify(PARTICIPANT_UID)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def outsider_client():
    from api import app
    from api_v2 import _require_token
    app.dependency_overrides[_require_token] = _fake_verify(OUTSIDER_UID)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_workspace(**kwargs) -> Workspace:
    defaults = dict(
        workspace_id="ws-1",
        title="Standups",
        type="shared",
        timezone="UTC",
        owner_uids=[ORGANIZER_UID],
        member_roles={
            ORGANIZER_UID: "organizer",
            PARTICIPANT_UID: "participant",
        },
    )
    defaults.update(kwargs)
    return Workspace(**defaults)


def _make_series(**kwargs) -> Series:
    defaults = dict(
        series_id="s-1",
        workspace_id="ws-1",
        kind="meeting",
        title="Weekly Standup",
        schedule_rule=ScheduleRule(frequency="weekly", weekdays=[1]),
        default_time="09:00",
        created_by=ORGANIZER_UID,
    )
    defaults.update(kwargs)
    return Series(**defaults)


def _make_occurrence(**kwargs) -> Occurrence:
    defaults = dict(
        occurrence_id="occ-1",
        series_id="s-1",
        workspace_id="ws-1",
        scheduled_for="2026-04-06T13:00:00+00:00",
    )
    defaults.update(kwargs)
    return Occurrence(**defaults)


# ---------------------------------------------------------------------------
# Workspace endpoints
# ---------------------------------------------------------------------------

class TestCreateWorkspace:
    def test_creates_workspace(self, organizer_client):
        with patch("workspace_storage.create_workspace") as mock_create,              patch("workspace_storage._get_client"):
            mock_create.side_effect = lambda ws: ws
            resp = organizer_client.post("/v2/workspaces", json={
                "title": "Team Standups",
                "type": "shared",
                "timezone": "America/New_York",
            }, headers=AUTH)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Team Standups"
        assert ORGANIZER_UID in data["owner_uids"]

    def test_returns_400_on_storage_error(self, organizer_client):
        with patch("workspace_storage.create_workspace", side_effect=ValueError("already exists")):
            # ValueError from create_workspace is unhandled and becomes 500
            resp = organizer_client.post("/v2/workspaces", json={
                "title": "X", "type": "shared",
            }, headers=AUTH)
        assert resp.status_code == 409


class TestGetWorkspace:
    def test_organizer_can_read(self, organizer_client):
        ws = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws):
            resp = organizer_client.get("/v2/workspaces/ws-1", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["workspace_id"] == "ws-1"

    def test_participant_can_read(self, participant_client):
        ws = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws):
            resp = participant_client.get("/v2/workspaces/ws-1", headers=AUTH)
        assert resp.status_code == 200

    def test_outsider_gets_403(self, outsider_client):
        ws = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws):
            resp = outsider_client.get("/v2/workspaces/ws-1", headers=AUTH)
        assert resp.status_code == 403

    def test_missing_gets_404(self, organizer_client):
        with patch("workspace_storage.get_workspace", return_value=None):
            resp = organizer_client.get("/v2/workspaces/no-such", headers=AUTH)
        assert resp.status_code == 404


class TestUpdateWorkspace:
    def test_organizer_can_update(self, organizer_client):
        ws = _make_workspace()
        updated = _make_workspace(title="New Title")
        with patch("workspace_storage.get_workspace", return_value=ws),              patch("workspace_storage.update_workspace", return_value=updated):
            resp = organizer_client.patch("/v2/workspaces/ws-1",
                                          json={"title": "New Title"}, headers=AUTH)
        assert resp.status_code == 200

    def test_participant_cannot_update(self, participant_client):
        ws = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws):
            resp = participant_client.patch("/v2/workspaces/ws-1",
                                            json={"title": "X"}, headers=AUTH)
        assert resp.status_code == 403


class TestDeleteWorkspace:
    def test_organizer_can_delete(self, organizer_client):
        ws = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws),              patch("workspace_storage.delete_workspace"):
            resp = organizer_client.delete("/v2/workspaces/ws-1", headers=AUTH)
        assert resp.status_code == 204

    def test_participant_cannot_delete(self, participant_client):
        ws = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws):
            resp = participant_client.delete("/v2/workspaces/ws-1", headers=AUTH)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------

class TestMemberManagement:
    def test_add_member(self, organizer_client):
        ws = _make_workspace()
        updated = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws),              patch("workspace_storage.add_member", return_value=updated):
            resp = organizer_client.post(
                "/v2/workspaces/ws-1/members",
                json={"uid": "uid-new", "role": "participant"},
                headers=AUTH,
            )
        assert resp.status_code == 201

    def test_participant_cannot_add_member(self, participant_client):
        ws = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws):
            resp = participant_client.post(
                "/v2/workspaces/ws-1/members",
                json={"uid": "uid-new", "role": "participant"},
                headers=AUTH,
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Series endpoints
# ---------------------------------------------------------------------------

class TestSeriesEndpoints:
    def test_create_series(self, organizer_client):
        ws = _make_workspace()
        series = _make_series()
        with patch("workspace_storage.get_workspace", return_value=ws),              patch("series_storage.create_series", side_effect=lambda s: s):
            resp = organizer_client.post(
                "/v2/workspaces/ws-1/series",
                json={
                    "kind": "meeting",
                    "title": "Weekly Standup",
                    "schedule_rule": {"frequency": "weekly", "weekdays": [1]},
                    "default_time": "09:00",
                },
                headers=AUTH,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["kind"] == "meeting"
        assert data["title"] == "Weekly Standup"

    def test_participant_cannot_create_series(self, participant_client):
        ws = _make_workspace()
        with patch("workspace_storage.get_workspace", return_value=ws):
            resp = participant_client.post(
                "/v2/workspaces/ws-1/series",
                json={"kind": "meeting", "title": "X",
                      "schedule_rule": {"frequency": "weekly"}},
                headers=AUTH,
            )
        assert resp.status_code == 403

    def test_list_series(self, participant_client):
        ws = _make_workspace()
        series = [_make_series()]
        with patch("workspace_storage.get_workspace", return_value=ws),              patch("series_storage.list_series_for_workspace", return_value=series):
            resp = participant_client.get("/v2/workspaces/ws-1/series", headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.json()["series"]) == 1

    def test_get_series(self, participant_client):
        ws = _make_workspace()
        series = _make_series()
        with patch("series_storage.get_series", return_value=series),              patch("workspace_storage.get_workspace", return_value=ws):
            resp = participant_client.get("/v2/series/s-1", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["series_id"] == "s-1"

    def test_get_series_not_found(self, organizer_client):
        with patch("series_storage.get_series", return_value=None):
            resp = organizer_client.get("/v2/series/no-such", headers=AUTH)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Occurrence endpoints
# ---------------------------------------------------------------------------

class TestOccurrenceEndpoints:
    def test_generate_occurrences(self, organizer_client):
        ws = _make_workspace()
        series = _make_series()
        new_occs = [_make_occurrence()]
        with patch("series_storage.get_series", return_value=series),              patch("workspace_storage.get_workspace", return_value=ws),              patch("api_v2.generate_and_save", return_value=new_occs):
            resp = organizer_client.post(
                "/v2/series/s-1/occurrences/generate",
                json={"start_date": "2026-04-01", "end_date": "2026-04-30"},
                headers=AUTH,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1

    def test_list_workspace_occurrences(self, participant_client):
        ws = _make_workspace()
        occs = [_make_occurrence()]
        with patch("workspace_storage.get_workspace", return_value=ws),              patch("series_storage.list_occurrences_for_workspace", return_value=occs):
            resp = participant_client.get("/v2/workspaces/ws-1/occurrences", headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.json()["occurrences"]) == 1

    def test_get_occurrence(self, participant_client):
        ws = _make_workspace()
        occ = _make_occurrence()
        with patch("series_storage.get_occurrence", return_value=occ),              patch("workspace_storage.get_workspace", return_value=ws):
            resp = participant_client.get("/v2/occurrences/occ-1", headers=AUTH)
        assert resp.status_code == 200

    def test_skip_occurrence(self, organizer_client):
        ws = _make_workspace()
        occ = _make_occurrence()
        cancelled = _make_occurrence(status="cancelled")
        with patch("series_storage.get_occurrence", return_value=occ),              patch("workspace_storage.get_workspace", return_value=ws),              patch("api_v2.skip_occurrence", return_value=cancelled):
            resp = organizer_client.patch(
                "/v2/occurrences/occ-1",
                json={"status": "cancelled"},
                headers=AUTH,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_participant_cannot_skip(self, participant_client):
        ws = _make_workspace()
        occ = _make_occurrence()
        with patch("series_storage.get_occurrence", return_value=occ),              patch("workspace_storage.get_workspace", return_value=ws):
            resp = participant_client.patch(
                "/v2/occurrences/occ-1",
                json={"status": "cancelled"},
                headers=AUTH,
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CheckIn endpoints
# ---------------------------------------------------------------------------

class TestCheckInEndpoints:
    def test_confirm_check_in(self, participant_client):
        ws = _make_workspace()
        occ = _make_occurrence()
        ci = CheckIn(
            check_in_id="ci-1", occurrence_id="occ-1", series_id="s-1",
            workspace_id="ws-1", user_id=PARTICIPANT_UID, status="confirmed",
        )
        with patch("series_storage.get_occurrence", return_value=occ),              patch("workspace_storage.get_workspace", return_value=ws),              patch("series_storage.get_check_in_for_user", return_value=None),              patch("series_storage.save_check_in", return_value=ci):
            resp = participant_client.post(
                "/v2/occurrences/occ-1/check-ins",
                json={"status": "confirmed"},
                headers=AUTH,
            )
        assert resp.status_code == 201

    def test_outsider_cannot_check_in(self, outsider_client):
        ws = _make_workspace()
        occ = _make_occurrence()
        with patch("series_storage.get_occurrence", return_value=occ),              patch("workspace_storage.get_workspace", return_value=ws):
            resp = outsider_client.post(
                "/v2/occurrences/occ-1/check-ins",
                json={"status": "confirmed"},
                headers=AUTH,
            )
        assert resp.status_code == 403

    def test_list_check_ins(self, participant_client):
        ws = _make_workspace()
        occ = _make_occurrence()
        ci = CheckIn(
            check_in_id="ci-1", occurrence_id="occ-1", series_id="s-1",
            workspace_id="ws-1", user_id=PARTICIPANT_UID,
        )
        with patch("series_storage.get_occurrence", return_value=occ),              patch("workspace_storage.get_workspace", return_value=ws),              patch("series_storage.list_check_ins_for_occurrence", return_value=[ci]):
            resp = participant_client.get("/v2/occurrences/occ-1/check-ins", headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.json()["check_ins"]) == 1
