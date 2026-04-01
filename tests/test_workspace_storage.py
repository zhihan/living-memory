"""Tests for room_storage.py using mocked Firestore."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

import room_storage
from models import Room
from room_storage import (
    ROOMS_COLLECTION,
    ROOM_INVITES_SUBCOLLECTION,
    accept_room_invite,
    add_member,
    create_room,
    create_room_invite,
    delete_room,
    find_room_invite,
    get_member_role,
    get_room,
    list_rooms_for_user,
    remove_member,
    update_room,
)


def _utcnow():
    return datetime.now(timezone.utc)


def _mock_doc(exists=True, data=None, doc_id="rm-1"):
    doc = MagicMock()
    doc.exists = exists
    doc.id = doc_id
    if data:
        doc.to_dict.return_value = data
    return doc


def _rm_data(**kwargs):
    defaults = {
        "room_id": "rm-1",
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
# create_room
# ---------------------------------------------------------------------------

class TestCreateRoom:
    def test_creates_document(self):
        rm = Room(
            room_id="rm-1",
            title="Standups",
            type="shared",
            timezone="UTC",
            owner_uids=["uid-alice"],
        )
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(exists=False)
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("room_storage._get_client", return_value=mock_db):
            result = create_room(rm)

        mock_ref.set.assert_called_once()
        assert result.room_id == "rm-1"
        assert result.created_at is not None

    def test_owner_added_to_member_roles(self):
        rm = Room(
            room_id="rm-1",
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

        with patch("room_storage._get_client", return_value=mock_db):
            result = create_room(rm)

        assert result.member_roles.get("uid-alice") == "organizer"

    def test_raises_if_no_owners(self):
        rm = Room(
            room_id="rm-1",
            title="Standups",
            type="shared",
            timezone="UTC",
            owner_uids=[],
        )
        with pytest.raises(ValueError, match="must have at least one owner"):
            create_room(rm)

    def test_raises_if_already_exists(self):
        rm = Room(
            room_id="rm-1",
            title="Standups",
            type="shared",
            timezone="UTC",
            owner_uids=["uid-alice"],
        )
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(exists=True)
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("room_storage._get_client", return_value=mock_db):
            with pytest.raises(ValueError, match="already exists"):
                create_room(rm)


# ---------------------------------------------------------------------------
# get_room
# ---------------------------------------------------------------------------

class TestGetRoom:
    def test_returns_room(self):
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_doc(data=_rm_data())
        )
        with patch("room_storage._get_client", return_value=mock_db):
            rm = get_room("rm-1")
        assert rm is not None
        assert rm.room_id == "rm-1"
        assert rm.title == "Team Standups"

    def test_returns_none_if_missing(self):
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_doc(exists=False)
        )
        with patch("room_storage._get_client", return_value=mock_db):
            rm = get_room("no-such-id")
        assert rm is None


# ---------------------------------------------------------------------------
# update_room
# ---------------------------------------------------------------------------

class TestUpdateRoom:
    def test_updates_fields(self):
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(data=_rm_data())
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("room_storage._get_client", return_value=mock_db):
            rm = update_room("rm-1", {"title": "New Title"})

        mock_ref.update.assert_called_once()
        update_args = mock_ref.update.call_args[0][0]
        assert update_args["title"] == "New Title"
        assert "updated_at" in update_args

    def test_raises_if_not_found(self):
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(exists=False)
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("room_storage._get_client", return_value=mock_db):
            with pytest.raises(ValueError, match="not found"):
                update_room("rm-missing", {"title": "x"})


# ---------------------------------------------------------------------------
# add_member / remove_member / get_member_role
# ---------------------------------------------------------------------------

class TestMemberManagement:
    def test_add_participant(self):
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_ref.get.return_value = _mock_doc(data=_rm_data())
        mock_db.collection.return_value.document.return_value = mock_ref

        # get_room is called again after update; return updated data
        data_after = _rm_data(member_roles={"uid-alice": "organizer", "uid-bob": "participant"})

        fake_firestore_v1 = types.ModuleType("google.cloud.firestore_v1")
        fake_firestore_v1.ArrayUnion = lambda vals: ("__array_union__", vals)
        with patch.dict(sys.modules, {"google.cloud.firestore_v1": fake_firestore_v1}):
            with patch("room_storage._get_client", return_value=mock_db):
                with patch("room_storage.get_room") as mock_get:
                    mock_get.return_value = Room.from_dict(data_after)
                    result = add_member("rm-1", "uid-bob", "participant")

        mock_ref.update.assert_called_once()
        update_args = mock_ref.update.call_args[0][0]
        assert "member_roles.uid-bob" in update_args
        assert update_args["member_roles.uid-bob"] == "participant"
        assert "member_uids" in update_args

    def test_get_member_role_returns_none_for_nonmember(self):
        data = _rm_data(member_roles={"uid-alice": "organizer"})
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_doc(data=data)
        )
        with patch("room_storage._get_client", return_value=mock_db):
            role = get_member_role("rm-1", "uid-unknown")
        assert role is None

    def test_remove_member_deletes_profile(self):
        data = _rm_data(
            member_roles={"uid-alice": "organizer", "uid-bob": "participant"},
            member_profiles={"uid-bob": {"display_name": "Bob", "email": "bob@example.com"}},
        )
        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref
        fake_firestore_v1 = types.ModuleType("google.cloud.firestore_v1")
        fake_firestore_v1.DELETE_FIELD = object()
        fake_firestore_v1.ArrayRemove = lambda vals: ("__array_remove__", vals)
        with patch.dict(sys.modules, {"google.cloud.firestore_v1": fake_firestore_v1}):
            with patch("room_storage._get_client", return_value=mock_db):
                with patch("room_storage.get_room", return_value=Room.from_dict(data)):
                    remove_member("rm-1", "uid-bob")
        update_args = mock_ref.update.call_args[0][0]
        assert "member_profiles.uid-bob" in update_args
        assert "member_uids" in update_args

    def test_remove_last_organizer_raises(self):
        data = _rm_data(member_roles={"uid-alice": "organizer"})
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_doc(data=data)
        )
        with patch("room_storage._get_client", return_value=mock_db):
            with patch("room_storage.get_room") as mock_get:
                mock_get.return_value = Room.from_dict(data)
                with pytest.raises(ValueError, match="last organizer"):
                    remove_member("rm-1", "uid-alice")


# ---------------------------------------------------------------------------
# create_room_invite / find / accept
# ---------------------------------------------------------------------------

class TestRoomInvites:
    def test_create_invite_returns_dict(self):
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.set.return_value = None
        mock_db.collection.return_value.document.return_value.set.return_value = None

        with patch("room_storage._get_client", return_value=mock_db):
            invite = create_room_invite("rm-1", "uid-alice", role="participant")

        assert "invite_id" in invite
        assert invite["room_id"] == "rm-1"
        assert invite["role"] == "participant"
        assert invite["accepted_by"] is None

    def test_find_invite_reads_lookup_doc_first(self):
        mock_db = MagicMock()
        lookup_doc = MagicMock()
        lookup_doc.exists = True
        lookup_doc.to_dict.return_value = {"invite_id": "inv-1", "room_id": "rm-1"}
        mock_db.collection.return_value.document.return_value.get.return_value = lookup_doc

        with patch("room_storage._get_client", return_value=mock_db):
            invite = find_room_invite("inv-1")

        assert invite == {"invite_id": "inv-1", "room_id": "rm-1"}

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Invalid role"):
            create_room_invite("rm-1", "uid-alice", role="superadmin")

    def test_accept_already_accepted_raises(self):
        invite_data = {
            "invite_id": "inv-1",
            "room_id": "rm-1",
            "created_by": "uid-alice",
            "created_at": _utcnow(),
            "expires_at": _utcnow() + timedelta(days=7),
            "accepted_by": "uid-charlie",  # already accepted
            "role": "participant",
        }
        with patch("room_storage.find_room_invite", return_value=invite_data):
            with pytest.raises(ValueError, match="already been accepted"):
                accept_room_invite("inv-1", "uid-bob")

    def test_accept_expired_raises(self):
        invite_data = {
            "invite_id": "inv-1",
            "room_id": "rm-1",
            "created_by": "uid-alice",
            "created_at": _utcnow() - timedelta(days=10),
            "expires_at": _utcnow() - timedelta(days=3),  # expired
            "accepted_by": None,
            "role": "participant",
        }
        with patch("room_storage.find_room_invite", return_value=invite_data):
            with pytest.raises(ValueError, match="expired"):
                accept_room_invite("inv-1", "uid-bob")

    def test_accept_not_found_raises(self):
        with patch("room_storage.find_room_invite", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                accept_room_invite("inv-missing", "uid-bob")
