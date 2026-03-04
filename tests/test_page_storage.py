"""Tests for the page storage module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import page_storage
from page_storage import (
    Page, Invite, AuditLogEntry, User,
    create_page, get_page, update_page, delete_page,
    list_pages_for_user, add_owner, remove_owner,
    create_invite, get_invite, find_invite, accept_invite,
    write_audit_log, get_or_create_user, get_user, update_user,
)


def _mock_doc(exists: bool = True, data: dict | None = None, doc_id: str = "doc1"):
    doc = MagicMock()
    doc.exists = exists
    doc.id = doc_id
    if data:
        doc.to_dict.return_value = data
    return doc


# ---------------------------------------------------------------------------
# Page data class
# ---------------------------------------------------------------------------

class TestPageModel:
    def test_to_dict(self):
        page = Page(slug="test", title="Test", visibility="public", owner_uids=["u1"])
        d = page.to_dict()
        assert d["title"] == "Test"
        assert d["visibility"] == "public"
        assert d["owner_uids"] == ["u1"]
        assert "created_at" in d

    def test_from_dict(self):
        data = {
            "title": "My Page",
            "visibility": "personal",
            "owner_uids": ["u1", "u2"],
            "description": "A test page",
        }
        page = Page.from_dict("my-page", data)
        assert page.slug == "my-page"
        assert page.title == "My Page"
        assert page.visibility == "personal"
        assert page.owner_uids == ["u1", "u2"]
        assert page.description == "A test page"

    def test_to_dict_includes_timezone(self):
        page = Page(slug="t", title="T", visibility="public", owner_uids=["u1"],
                    timezone="America/Chicago")
        d = page.to_dict()
        assert d["timezone"] == "America/Chicago"

    def test_to_dict_timezone_none_by_default(self):
        page = Page(slug="t", title="T", visibility="public", owner_uids=["u1"])
        d = page.to_dict()
        assert d["timezone"] is None

    def test_from_dict_with_timezone(self):
        data = {"title": "T", "visibility": "public", "owner_uids": ["u1"],
                "timezone": "Europe/London"}
        page = Page.from_dict("t", data)
        assert page.timezone == "Europe/London"

    def test_from_dict_without_timezone_backwards_compat(self):
        data = {"title": "T", "visibility": "public", "owner_uids": ["u1"]}
        page = Page.from_dict("t", data)
        assert page.timezone is None


# ---------------------------------------------------------------------------
# Page CRUD
# ---------------------------------------------------------------------------

class TestCreatePage:
    @patch("page_storage._get_client")
    def test_create_success(self, mock_gc):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db
        mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(exists=False)

        page = Page(slug="test-page", title="Test", visibility="public", owner_uids=["u1"])
        result = create_page(page)

        assert result.slug == "test-page"
        assert result.created_at is not None
        mock_db.collection.return_value.document.return_value.set.assert_called_once()

    @patch("page_storage._get_client")
    def test_create_no_owners_raises(self, mock_gc):
        page = Page(slug="test", title="Test", visibility="public", owner_uids=[])
        with pytest.raises(ValueError, match="at least one owner"):
            create_page(page)

    @patch("page_storage._get_client")
    def test_create_invalid_visibility_raises(self, mock_gc):
        page = Page(slug="test", title="Test", visibility="hidden", owner_uids=["u1"])
        with pytest.raises(ValueError, match="Visibility"):
            create_page(page)

    @patch("page_storage._get_client")
    def test_create_duplicate_raises(self, mock_gc):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db
        mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(exists=True)

        page = Page(slug="dupe", title="Dupe", visibility="public", owner_uids=["u1"])
        with pytest.raises(ValueError, match="already exists"):
            create_page(page)


class TestGetPage:
    @patch("page_storage._get_client")
    def test_found(self, mock_gc):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db
        data = {"title": "My Page", "visibility": "public", "owner_uids": ["u1"]}
        mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(data=data)

        result = get_page("my-page")
        assert result is not None
        assert result.slug == "my-page"
        assert result.title == "My Page"

    @patch("page_storage._get_client")
    def test_not_found(self, mock_gc):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db
        mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(exists=False)

        result = get_page("nonexistent")
        assert result is None


class TestRemoveOwner:
    @patch("page_storage.get_page")
    @patch("page_storage._get_client")
    def test_remove_one_of_two(self, mock_gc, mock_get):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db
        mock_get.side_effect = [
            Page(slug="s", title="T", visibility="public", owner_uids=["u1", "u2"]),
            Page(slug="s", title="T", visibility="public", owner_uids=["u1"]),
        ]

        result = remove_owner("s", "u2")
        assert "u2" not in result.owner_uids

    @patch("page_storage.get_page")
    def test_remove_last_owner_raises(self, mock_get):
        mock_get.return_value = Page(slug="s", title="T", visibility="public", owner_uids=["u1"])
        with pytest.raises(ValueError, match="last owner"):
            remove_owner("s", "u1")

    @patch("page_storage.get_page")
    def test_remove_non_owner_raises(self, mock_get):
        mock_get.return_value = Page(slug="s", title="T", visibility="public", owner_uids=["u1"])
        with pytest.raises(ValueError, match="not an owner"):
            remove_owner("s", "u2")


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------

class TestInvites:
    @patch("page_storage._get_client")
    def test_create_invite(self, mock_gc):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db

        invite = create_invite("my-page", "owner-uid")
        assert invite.page_slug == "my-page"
        assert invite.created_by == "owner-uid"
        assert invite.invite_id  # non-empty

    @patch("page_storage.write_audit_log")
    @patch("page_storage.add_owner")
    @patch("page_storage.find_invite")
    @patch("page_storage._get_client")
    def test_accept_invite(self, mock_gc, mock_find, mock_add_owner, mock_audit):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db
        now = datetime.now(timezone.utc)
        mock_find.return_value = Invite(
            invite_id="inv-1",
            page_slug="my-page",
            created_by="owner-uid",
            created_at=now,
            expires_at=now + timedelta(days=7),
            accepted_by=None,
        )

        result = accept_invite("inv-1", "new-user")
        assert result.accepted_by == "new-user"
        mock_add_owner.assert_called_once_with("my-page", "new-user")
        mock_audit.assert_called_once()

    @patch("page_storage.find_invite")
    def test_accept_already_accepted_raises(self, mock_find):
        mock_find.return_value = Invite(
            invite_id="inv-1", page_slug="p", created_by="u1",
            accepted_by="u2",
        )
        with pytest.raises(ValueError, match="already been accepted"):
            accept_invite("inv-1", "u3")

    @patch("page_storage.find_invite")
    def test_accept_expired_raises(self, mock_find):
        past = datetime.now(timezone.utc) - timedelta(days=10)
        mock_find.return_value = Invite(
            invite_id="inv-1", page_slug="p", created_by="u1",
            expires_at=past,
        )
        with pytest.raises(ValueError, match="expired"):
            accept_invite("inv-1", "u3")

    @patch("page_storage.find_invite")
    def test_accept_not_found_raises(self, mock_find):
        mock_find.return_value = None
        with pytest.raises(ValueError, match="not found"):
            accept_invite("inv-1", "u3")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    @patch("page_storage._get_client")
    def test_write_audit_log(self, mock_gc):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db

        entry = write_audit_log(
            page_slug="my-page",
            action="owner_added",
            actor_uid="u1",
            target_uid="u2",
            metadata={"invite_id": "inv-1"},
        )
        assert entry.page_slug == "my-page"
        assert entry.action == "owner_added"
        assert entry.actor_uid == "u1"
        assert entry.target_uid == "u2"
        mock_db.collection.return_value.document.return_value.set.assert_called_once()


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

class TestUserProfile:
    @patch("page_storage._get_client")
    def test_get_or_create_new(self, mock_gc):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db
        mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(exists=False)

        user = get_or_create_user("uid-1", display_name="Alice")
        assert user.uid == "uid-1"
        assert user.display_name == "Alice"
        mock_db.collection.return_value.document.return_value.set.assert_called_once()

    @patch("page_storage._get_client")
    def test_get_or_create_existing(self, mock_gc):
        mock_db = MagicMock()
        mock_gc.return_value = mock_db
        data = {"uid": "uid-1", "display_name": "Alice", "photo_url": None,
                "default_personal_page_id": "p1"}
        mock_db.collection.return_value.document.return_value.get.return_value = _mock_doc(data=data)

        user = get_or_create_user("uid-1")
        assert user.uid == "uid-1"
        assert user.default_personal_page_id == "p1"
        mock_db.collection.return_value.document.return_value.set.assert_not_called()


# ---------------------------------------------------------------------------
# Soft-delete and restore
# ---------------------------------------------------------------------------

class TestSoftDeletePage:
    @patch("page_storage.update_page")
    @patch("firestore_storage.save_memory")
    @patch("firestore_storage.load_memories_by_page")
    def test_soft_delete_page(self, mock_load, mock_save, mock_update):
        from datetime import date
        from memory import Memory

        mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Test", title="Event", page_id="my-page",
        )
        mock_load.return_value = [("m1", mem)]
        mock_update.return_value = Page(
            slug="my-page", title="Test", visibility="public",
            owner_uids=["u1"],
            delete_after=datetime.now(timezone.utc) + timedelta(days=30),
        )

        result = page_storage.soft_delete_page("my-page")

        assert result.delete_after is not None
        mock_save.assert_called_once()
        saved_mem = mock_save.call_args[0][0]
        assert saved_mem.expires == date.today() + timedelta(days=30)

    @patch("page_storage.update_page")
    @patch("firestore_storage.save_memory")
    @patch("firestore_storage.load_memories_by_page")
    @patch("page_storage.get_page")
    def test_restore_page(self, mock_get, mock_load, mock_save, mock_update):
        from datetime import date
        from memory import Memory

        deadline = datetime.now(timezone.utc) + timedelta(days=30)
        mock_get.return_value = Page(
            slug="my-page", title="Test", visibility="public",
            owner_uids=["u1"], delete_after=deadline,
        )
        mem = Memory(
            target=date(2026, 3, 5), expires=deadline.date(),
            content="Test", title="Event", page_id="my-page",
        )
        mock_load.return_value = [("m1", mem)]
        mock_update.return_value = Page(
            slug="my-page", title="Test", visibility="public",
            owner_uids=["u1"], delete_after=None,
        )

        result = page_storage.restore_page("my-page")

        assert result.delete_after is None
        mock_save.assert_called_once()
        saved_mem = mock_save.call_args[0][0]
        assert saved_mem.expires == date(9999, 12, 31)

    @patch("page_storage.get_page")
    def test_restore_page_not_deleted_raises(self, mock_get):
        mock_get.return_value = Page(
            slug="my-page", title="Test", visibility="public",
            owner_uids=["u1"], delete_after=None,
        )
        with pytest.raises(ValueError, match="not pending deletion"):
            page_storage.restore_page("my-page")


class TestPageDeleteAfterRoundtrip:
    def test_to_dict_with_delete_after(self):
        deadline = datetime(2026, 3, 26, tzinfo=timezone.utc)
        page = Page(
            slug="test", title="Test", visibility="public",
            owner_uids=["u1"], delete_after=deadline,
        )
        d = page.to_dict()
        assert d["delete_after"] == deadline

    def test_to_dict_without_delete_after(self):
        page = Page(slug="test", title="Test", visibility="public", owner_uids=["u1"])
        d = page.to_dict()
        assert d["delete_after"] is None

    def test_from_dict_with_delete_after(self):
        deadline = datetime(2026, 3, 26, tzinfo=timezone.utc)
        data = {
            "title": "Test", "visibility": "public",
            "owner_uids": ["u1"], "delete_after": deadline,
        }
        page = Page.from_dict("test", data)
        assert page.delete_after == deadline

    def test_from_dict_without_delete_after(self):
        data = {"title": "Test", "visibility": "public", "owner_uids": ["u1"]}
        page = Page.from_dict("test", data)
        assert page.delete_after is None
