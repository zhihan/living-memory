"""Tests for workspace_storage.py using mocked Firestore."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

import workspace_storage
from models import Workspace
from workspace_storage import (
    WORKSPACES_COLLECTION,
    WORKSPACE_INVITES_SUBCOLLECTION,
    accept_workspace_invite,
    add_member,
    create_workspace,
    create_workspace_invite,
    delete_workspace,
    find_workspace_invite,
    get_member_role,
    get_workspace,
    list_workspaces_for_user,
    remove_member,
    update_workspace,
)


def _utcnow():
    return datetime.now(timezone.utc)


def _mock_doc(exists=True, data=None, doc_id="ws-1"):
    doc = MagicMock()
    doc.exists = exists
    doc.id = doc_id
    if data:
        doc.to_dict.return_value = data
    return doc


def _ws_data(**kwargs):
    defaults = {
        "workspace_id": "ws-1",
        "title": "Team Standups",
        "type": "shared",
        "timezone": "UTC",
        "owner_uids": ["uid-alice"],
        "member_roles": {"uid-alice": "organizer"},
        "description": None,
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# create_workspace
# ---------------------------------------------------------------------------

class TestCreateWorkspace:
    def test_creates_document(self):
        ws = Workspace(
            workspace_id="ws-1",
            title="Standups",
            type="shared",
            timezone="UTC",
            owner_uids=["uid-alice"],
        )
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(exists=False)
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("workspace_storage._get_client", return_value=mock_db):
            result = create_workspace(ws)

        mock_ref.set.assert_called_once()
        assert result.workspace_id == "ws-1"
        assert result.created_at is not None

    def test_owner_added_to_member_roles(self):
        ws = Workspace(
            workspace_id="ws-1",
            title="Standups",
            type="shared",
            timezone="UTC",
            owner_uids=["uid-alice"],
            member_roles={},
        )
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(exists=False)
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("workspace_storage._get_client", return_value=mock_db):
            result = create_workspace(ws)

        assert result.member_roles.get("uid-alice") == "organizer"

    def test_raises_if_no_owners(self):
        ws = Workspace(
            workspace_id="ws-1",
            title="Standups",
            type="shared",
            timezone="UTC",
            owner_uids=[],
        )
        with pytest.raises(ValueError, match="must have at least one owner"):
            create_workspace(ws)

    def test_raises_if_already_exists(self):
        ws = Workspace(
            workspace_id="ws-1",
            title="Standups",
            type="shared",
            timezone="UTC",
            owner_uids=["uid-alice"],
        )
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(exists=True)
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("workspace_storage._get_client", return_value=mock_db):
            with pytest.raises(ValueError, match="already exists"):
                create_workspace(ws)


# ---------------------------------------------------------------------------
# get_workspace
# ---------------------------------------------------------------------------

class TestGetWorkspace:
    def test_returns_workspace(self):
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_doc(data=_ws_data())
        )
        with patch("workspace_storage._get_client", return_value=mock_db):
            ws = get_workspace("ws-1")
        assert ws is not None
        assert ws.workspace_id == "ws-1"
        assert ws.title == "Team Standups"

    def test_returns_none_if_missing(self):
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_doc(exists=False)
        )
        with patch("workspace_storage._get_client", return_value=mock_db):
            ws = get_workspace("no-such-id")
        assert ws is None


# ---------------------------------------------------------------------------
# update_workspace
# ---------------------------------------------------------------------------

class TestUpdateWorkspace:
    def test_updates_fields(self):
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(data=_ws_data())
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("workspace_storage._get_client", return_value=mock_db):
            ws = update_workspace("ws-1", {"title": "New Title"})

        mock_ref.update.assert_called_once()
        update_args = mock_ref.update.call_args[0][0]
        assert update_args["title"] == "New Title"
        assert "updated_at" in update_args

    def test_raises_if_not_found(self):
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(exists=False)
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("workspace_storage._get_client", return_value=mock_db):
            with pytest.raises(ValueError, match="not found"):
                update_workspace("ws-missing", {"title": "x"})


# ---------------------------------------------------------------------------
# add_member / remove_member / get_member_role
# ---------------------------------------------------------------------------

class TestMemberManagement:
    def test_add_participant(self):
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(data=_ws_data())
        mock_db.collection.return_value.document.return_value = mock_ref

        # get_workspace is called again after update; return updated data
        data_after = _ws_data(member_roles={"uid-alice": "organizer", "uid-bob": "participant"})
        mock_doc_after = _mock_doc(data=data_after)
        # First call: exists check inside add_member; second: get_workspace return
        mock_ref.get.side_effect = [_mock_doc(data=_ws_data()), mock_doc_after]

        with patch("workspace_storage._get_client", return_value=mock_db):
            with patch("workspace_storage.get_workspace") as mock_get:
                mock_get.return_value = Workspace.from_dict(data_after)
                result = add_member("ws-1", "uid-bob", "participant")

        mock_ref.update.assert_called_once()
        update_args = mock_ref.update.call_args[0][0]
        assert "member_roles.uid-bob" in update_args
        assert update_args["member_roles.uid-bob"] == "participant"

    def test_get_member_role_returns_none_for_nonmember(self):
        data = _ws_data(member_roles={"uid-alice": "organizer"})
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_doc(data=data)
        )
        with patch("workspace_storage._get_client", return_value=mock_db):
            role = get_member_role("ws-1", "uid-unknown")
        assert role is None

    def test_remove_last_organizer_raises(self):
        data = _ws_data(member_roles={"uid-alice": "organizer"})
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_doc(data=data)
        )
        with patch("workspace_storage._get_client", return_value=mock_db):
            with patch("workspace_storage.get_workspace") as mock_get:
                mock_get.return_value = Workspace.from_dict(data)
                with pytest.raises(ValueError, match="last organizer"):
                    remove_member("ws-1", "uid-alice")


# ---------------------------------------------------------------------------
# create_workspace_invite / find / accept
# ---------------------------------------------------------------------------

class TestWorkspaceInvites:
    def test_create_invite_returns_dict(self):
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.set.return_value = None

        with patch("workspace_storage._get_client", return_value=mock_db):
            invite = create_workspace_invite("ws-1", "uid-alice", role="participant")

        assert "invite_id" in invite
        assert invite["workspace_id"] == "ws-1"
        assert invite["role"] == "participant"
        assert invite["accepted_by"] is None

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Invalid role"):
            create_workspace_invite("ws-1", "uid-alice", role="superadmin")

    def test_accept_already_accepted_raises(self):
        invite_data = {
            "invite_id": "inv-1",
            "workspace_id": "ws-1",
            "created_by": "uid-alice",
            "created_at": _utcnow(),
            "expires_at": _utcnow() + timedelta(days=7),
            "accepted_by": "uid-charlie",  # already accepted
            "role": "participant",
        }
        with patch("workspace_storage.find_workspace_invite", return_value=invite_data):
            with pytest.raises(ValueError, match="already been accepted"):
                accept_workspace_invite("inv-1", "uid-bob")

    def test_accept_expired_raises(self):
        invite_data = {
            "invite_id": "inv-1",
            "workspace_id": "ws-1",
            "created_by": "uid-alice",
            "created_at": _utcnow() - timedelta(days=10),
            "expires_at": _utcnow() - timedelta(days=3),  # expired
            "accepted_by": None,
            "role": "participant",
        }
        with patch("workspace_storage.find_workspace_invite", return_value=invite_data):
            with pytest.raises(ValueError, match="expired"):
                accept_workspace_invite("inv-1", "uid-bob")

    def test_accept_not_found_raises(self):
        with patch("workspace_storage.find_workspace_invite", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                accept_workspace_invite("inv-missing", "uid-bob")
