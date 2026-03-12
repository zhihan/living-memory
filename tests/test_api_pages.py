"""Tests for the page-scoped API endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from memory import Memory
from committer import CommitResult
from page_storage import Page, Invite, User, AuditLogEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

OWNER_UID = "owner-uid-123"
OTHER_UID = "other-uid-456"
MEMBER_UID = "member-uid-789"


def _fake_verify(uid: str):
    """Return a mock Firebase token verifier that always returns the given uid."""
    def verifier(authorization: str = ""):
        return {"uid": uid}
    return verifier


@pytest.fixture
def client():
    """Test client with Firebase auth mocked to return OWNER_UID."""
    from api import app, _verify_firebase_token
    app.dependency_overrides[_verify_firebase_token] = _fake_verify(OWNER_UID)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def other_client():
    """Test client with Firebase auth mocked to return OTHER_UID (non-owner)."""
    from api import app, _verify_firebase_token
    app.dependency_overrides[_verify_firebase_token] = _fake_verify(OTHER_UID)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def member_client():
    """Test client with Firebase auth mocked to return MEMBER_UID (member, not owner)."""
    from api import app, _verify_firebase_token
    app.dependency_overrides[_verify_firebase_token] = _fake_verify(MEMBER_UID)
    yield TestClient(app)
    app.dependency_overrides.clear()


AUTH = {"Authorization": "Bearer fake-firebase-token"}
PUBLIC_PAGE = Page(
    slug="public-page", title="Public", visibility="public",
    owner_uids=[OWNER_UID],
)
PERSONAL_PAGE = Page(
    slug="personal-page", title="Personal", visibility="personal",
    owner_uids=[OWNER_UID],
)
PUBLIC_PAGE_WITH_MEMBER = Page(
    slug="public-page", title="Public", visibility="public",
    owner_uids=[OWNER_UID], member_uids=[MEMBER_UID],
)
PERSONAL_PAGE_WITH_MEMBER = Page(
    slug="personal-page", title="Personal", visibility="personal",
    owner_uids=[OWNER_UID], member_uids=[MEMBER_UID],
)


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    @patch("api.page_storage.get_or_create_user")
    def test_returns_user(self, mock_get, client):
        mock_get.return_value = User(uid=OWNER_UID, display_name="Alice")
        resp = client.get("/users/me", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["user"]["uid"] == OWNER_UID


# ---------------------------------------------------------------------------
# GET /users/me/pages
# ---------------------------------------------------------------------------

class TestListMyPages:
    @patch("api.page_storage.list_pages_for_user")
    def test_returns_owned_pages(self, mock_list, client):
        mock_list.return_value = [PUBLIC_PAGE, PERSONAL_PAGE]
        resp = client.get("/users/me/pages", headers=AUTH)
        assert resp.status_code == 200
        pages = resp.json()["pages"]
        assert len(pages) == 2
        assert pages[0]["slug"] == "public-page"
        assert pages[1]["slug"] == "personal-page"
        mock_list.assert_called_once_with(OWNER_UID)

    @patch("api.page_storage.list_pages_for_user")
    def test_returns_empty_list(self, mock_list, client):
        mock_list.return_value = []
        resp = client.get("/users/me/pages", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["pages"] == []


# ---------------------------------------------------------------------------
# POST /pages
# ---------------------------------------------------------------------------

class TestCreatePage:
    @patch("api.page_storage.create_page")
    def test_create_success(self, mock_create, client):
        mock_create.return_value = PUBLIC_PAGE
        resp = client.post("/pages", json={
            "slug": "public-page", "title": "Public", "visibility": "public",
        }, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"]["slug"] == "public-page"
        assert data["page"]["owner_uids"] == [OWNER_UID]

    @patch("api.page_storage.create_page")
    def test_create_duplicate_returns_400(self, mock_create, client):
        mock_create.side_effect = ValueError("Page 'dupe' already exists")
        resp = client.post("/pages", json={
            "slug": "dupe", "title": "Dupe",
        }, headers=AUTH)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /pages/{slug}
# ---------------------------------------------------------------------------

class TestGetPage:
    @patch("api.page_storage.get_page")
    def test_public_page_no_auth(self, mock_get):
        """Public pages should be readable without auth."""
        mock_get.return_value = PUBLIC_PAGE
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/public-page")
        assert resp.status_code == 200
        assert resp.json()["page"]["slug"] == "public-page"

    @patch("api.page_storage.get_page")
    def test_personal_page_no_auth_returns_401(self, mock_get):
        mock_get.return_value = PERSONAL_PAGE
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/personal-page")
        assert resp.status_code == 401

    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_personal_page_owner_can_read(self, mock_get, mock_verify):
        mock_get.return_value = PERSONAL_PAGE
        mock_verify.return_value = {"uid": OWNER_UID}
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/personal-page", headers=AUTH)
        assert resp.status_code == 200

    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_personal_page_non_owner_returns_403(self, mock_get, mock_verify):
        mock_get.return_value = PERSONAL_PAGE
        mock_verify.return_value = {"uid": OTHER_UID}
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/personal-page", headers=AUTH)
        assert resp.status_code == 403

    @patch("api.page_storage.get_page")
    def test_not_found_returns_404(self, mock_get):
        mock_get.return_value = None
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /pages/{slug}/owners/{uid}
# ---------------------------------------------------------------------------

class TestRemoveOwner:
    @patch("api.page_storage.write_audit_log")
    @patch("api.page_storage.remove_owner")
    @patch("api.page_storage.get_page")
    def test_remove_co_owner(self, mock_get, mock_remove, mock_audit, client):
        mock_get.return_value = PUBLIC_PAGE
        mock_remove.return_value = Page(
            slug="public-page", title="Public", visibility="public",
            owner_uids=[OWNER_UID],
        )
        resp = client.delete(f"/pages/public-page/owners/{OTHER_UID}", headers=AUTH)
        assert resp.status_code == 200
        mock_audit.assert_called_once()

    @patch("api.page_storage.get_page")
    def test_non_owner_returns_403(self, mock_get, other_client):
        mock_get.return_value = PUBLIC_PAGE  # OTHER_UID is not in owner_uids
        resp = other_client.delete(f"/pages/public-page/owners/{OWNER_UID}", headers=AUTH)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /pages/{slug}/invites
# ---------------------------------------------------------------------------

class TestCreateInvite:
    @patch("api.page_storage.write_audit_log")
    @patch("api.page_storage.create_invite")
    @patch("api.page_storage.get_page")
    def test_owner_can_create_invite(self, mock_get, mock_create, mock_audit, client):
        mock_get.return_value = PUBLIC_PAGE
        mock_create.return_value = Invite(
            invite_id="inv-1", page_slug="public-page", created_by=OWNER_UID,
        )
        resp = client.post("/pages/public-page/invites", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["invite"]["invite_id"] == "inv-1"
        mock_audit.assert_called_once()

    @patch("api.page_storage.get_page")
    def test_non_owner_returns_403(self, mock_get, other_client):
        mock_get.return_value = PUBLIC_PAGE
        resp = other_client.post("/pages/public-page/invites", headers=AUTH)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /invites/{id}/accept
# ---------------------------------------------------------------------------

class TestAcceptInvite:
    @patch("api.page_storage.accept_invite")
    def test_accept_success(self, mock_accept, other_client):
        mock_accept.return_value = Invite(
            invite_id="inv-1", page_slug="public-page",
            created_by=OWNER_UID, accepted_by=OTHER_UID,
        )
        resp = other_client.post("/invites/inv-1/accept", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["page_slug"] == "public-page"

    @patch("api.page_storage.accept_invite")
    def test_accept_expired_returns_400(self, mock_accept, other_client):
        mock_accept.side_effect = ValueError("Invite has expired")
        resp = other_client.post("/invites/inv-1/accept", headers=AUTH)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Page-scoped memory endpoints
# ---------------------------------------------------------------------------

class TestPageMemories:
    @patch("api.commit_memory_firestore")
    @patch("api.page_storage.get_page")
    def test_create_memory_on_page(self, mock_get, mock_commit, client):
        mock_get.return_value = PUBLIC_PAGE
        mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Test", title="Meeting", page_id="public-page",
        )
        mock_commit.return_value = [CommitResult(action="created", doc_id="m1", memory=mem)]
        resp = client.post("/pages/public-page/memories",
                           json={"message": "Team meeting"}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["memories"][0]["id"] == "m1"
        mock_commit.assert_called_once()
        call_kwargs = mock_commit.call_args[1]
        assert call_kwargs["message"] == "Team meeting"
        assert call_kwargs["attachment_urls"] is None
        assert call_kwargs["page_id"] == "public-page"
        assert "today" in call_kwargs, "API must pass today= explicitly"

    @patch("api.page_storage.get_page")
    def test_create_memory_non_owner_returns_403(self, mock_get, other_client):
        mock_get.return_value = PUBLIC_PAGE
        resp = other_client.post("/pages/public-page/memories",
                                 json={"message": "hi"}, headers=AUTH)
        assert resp.status_code == 403

    @patch("api.commit_memory_firestore")
    @patch("api.page_storage.get_page")
    def test_create_memory_ai_failure_returns_502(self, mock_get, mock_commit, client):
        """When the AI backend fails (e.g. empty response), return 502 with a clear message."""
        mock_get.return_value = PUBLIC_PAGE
        mock_commit.side_effect = Exception("Expecting value: line 1 column 1 (char 0)")
        resp = client.post("/pages/public-page/memories",
                           json={"message": "test message"}, headers=AUTH)
        assert resp.status_code == 502
        assert "AI backend" in resp.json()["detail"]

    @patch("api.firestore_storage.load_memories_by_page")
    @patch("api.page_storage.get_page")
    def test_list_public_page_memories_no_auth(self, mock_get, mock_load):
        """Public page memories are readable without auth."""
        mock_get.return_value = PUBLIC_PAGE
        mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Test", title="Event", page_id="public-page",
        )
        mock_load.return_value = [("m1", mem)]
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/public-page/memories")
        assert resp.status_code == 200
        assert len(resp.json()["memories"]) == 1

    @patch("api.page_storage.get_page")
    def test_list_personal_page_memories_no_auth_returns_401(self, mock_get):
        mock_get.return_value = PERSONAL_PAGE
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/personal-page/memories")
        assert resp.status_code == 401

    @patch("api.firestore_storage.load_memories_by_page")
    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_list_personal_page_memories_owner(self, mock_get, mock_verify, mock_load):
        mock_get.return_value = PERSONAL_PAGE
        mock_verify.return_value = {"uid": OWNER_UID}
        mock_load.return_value = []
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/personal-page/memories", headers=AUTH)
        assert resp.status_code == 200

    @patch("api.firestore_storage.load_memories_by_page")
    @patch("api.page_storage.get_page")
    def test_members_only_memory_hidden_from_public(self, mock_get, mock_load):
        """Members-only memories are filtered out for unauthenticated requests on public pages."""
        mock_get.return_value = PUBLIC_PAGE
        public_mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Public event", page_id="public-page", visibility="public",
        )
        members_mem = Memory(
            target=date(2026, 3, 6), expires=date(2026, 4, 5),
            content="Members event", page_id="public-page", visibility="members",
        )
        mock_load.return_value = [("m1", public_mem), ("m2", members_mem)]
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/public-page/memories")
        assert resp.status_code == 200
        memories = resp.json()["memories"]
        assert len(memories) == 1
        assert memories[0]["id"] == "m1"

    @patch("api.firestore_storage.load_memories_by_page")
    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_members_only_memory_visible_to_owner(self, mock_get, mock_verify, mock_load):
        """Members-only memories are visible to authenticated owners on public pages."""
        mock_get.return_value = PUBLIC_PAGE
        mock_verify.return_value = {"uid": OWNER_UID}
        public_mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Public event", page_id="public-page", visibility="public",
        )
        members_mem = Memory(
            target=date(2026, 3, 6), expires=date(2026, 4, 5),
            content="Members event", page_id="public-page", visibility="members",
        )
        mock_load.return_value = [("m1", public_mem), ("m2", members_mem)]
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/public-page/memories", headers=AUTH)
        assert resp.status_code == 200
        memories = resp.json()["memories"]
        assert len(memories) == 2

    @patch("api.commit_memory_firestore")
    @patch("api.page_storage.get_page")
    def test_create_memory_passes_visibility(self, mock_get, mock_commit, client):
        """POST /pages/{slug}/memories passes visibility to commit_memory_firestore."""
        mock_get.return_value = PUBLIC_PAGE
        mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Private meeting", page_id="public-page", visibility="members",
        )
        mock_commit.return_value = [CommitResult(action="created", doc_id="m1", memory=mem)]
        resp = client.post("/pages/public-page/memories",
                           json={"message": "Private meeting", "visibility": "members"},
                           headers=AUTH)
        assert resp.status_code == 200
        call_kwargs = mock_commit.call_args[1]
        assert call_kwargs["visibility"] == "members"

    @patch("api.firestore_storage.delete_memory")
    @patch("api.firestore_storage.get_memory")
    @patch("api.page_storage.get_page")
    def test_delete_memory_on_page(self, mock_get, mock_get_mem, mock_del, client):
        mock_get.return_value = PUBLIC_PAGE
        mock_get_mem.return_value = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Test", page_id="public-page",
        )
        resp = client.delete("/pages/public-page/memories/m1", headers=AUTH)
        assert resp.status_code == 200
        mock_del.assert_called_once_with("m1")

    @patch("api.firestore_storage.get_memory")
    @patch("api.page_storage.get_page")
    def test_delete_memory_wrong_page_returns_404(self, mock_get, mock_get_mem, client):
        mock_get.return_value = PUBLIC_PAGE
        mock_get_mem.return_value = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Test", page_id="different-page",
        )
        resp = client.delete("/pages/public-page/memories/m1", headers=AUTH)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /pages/{slug}
# ---------------------------------------------------------------------------

class TestUpdatePage:
    @patch("api.page_storage.write_audit_log")
    @patch("api.page_storage.update_page")
    @patch("api.page_storage.get_page")
    def test_patch_page_rename(self, mock_get, mock_update, mock_audit, client):
        mock_get.return_value = PUBLIC_PAGE
        updated = Page(
            slug="public-page", title="New Title", visibility="public",
            owner_uids=[OWNER_UID],
        )
        mock_update.return_value = updated
        resp = client.patch("/pages/public-page", json={"title": "New Title"}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["page"]["title"] == "New Title"
        mock_update.assert_called_once_with("public-page", {"title": "New Title"})
        mock_audit.assert_called_once()

    @patch("api.page_storage.get_page")
    def test_patch_page_not_owner(self, mock_get, other_client):
        mock_get.return_value = PUBLIC_PAGE
        resp = other_client.patch("/pages/public-page", json={"title": "X"}, headers=AUTH)
        assert resp.status_code == 403

    @patch("api.page_storage.get_page")
    def test_patch_page_empty_body(self, mock_get, client):
        mock_get.return_value = PUBLIC_PAGE
        resp = client.patch("/pages/public-page", json={}, headers=AUTH)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /pages/{slug}
# ---------------------------------------------------------------------------

class TestDeletePage:
    @patch("api.page_storage.write_audit_log")
    @patch("api.page_storage.soft_delete_page")
    @patch("api.page_storage.get_page")
    def test_delete_page_soft(self, mock_get, mock_soft_del, mock_audit, client):
        mock_get.return_value = PUBLIC_PAGE
        deadline = datetime(2026, 3, 26, tzinfo=timezone.utc)
        mock_soft_del.return_value = Page(
            slug="public-page", title="Public", visibility="public",
            owner_uids=[OWNER_UID], delete_after=deadline,
        )
        resp = client.delete("/pages/public-page", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_soft_del.assert_called_once_with("public-page")
        mock_audit.assert_called_once()

    @patch("api.page_storage.get_page")
    def test_delete_page_not_owner(self, mock_get, other_client):
        mock_get.return_value = PUBLIC_PAGE
        resp = other_client.delete("/pages/public-page", headers=AUTH)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /pages/{slug}/restore
# ---------------------------------------------------------------------------

class TestRestorePage:
    @patch("api.page_storage.write_audit_log")
    @patch("api.page_storage.restore_page")
    @patch("api.page_storage.get_page")
    def test_restore_page(self, mock_get, mock_restore, mock_audit, client):
        deadline = datetime(2026, 3, 26, tzinfo=timezone.utc)
        mock_get.return_value = Page(
            slug="public-page", title="Public", visibility="public",
            owner_uids=[OWNER_UID], delete_after=deadline,
        )
        restored = Page(
            slug="public-page", title="Public", visibility="public",
            owner_uids=[OWNER_UID], delete_after=None,
        )
        mock_restore.return_value = restored
        resp = client.post("/pages/public-page/restore", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["page"]["delete_after"] is None
        mock_restore.assert_called_once_with("public-page")
        mock_audit.assert_called_once()

    @patch("api.page_storage.restore_page")
    @patch("api.page_storage.get_page")
    def test_restore_page_not_deleted(self, mock_get, mock_restore, client):
        mock_get.return_value = PUBLIC_PAGE  # delete_after is None
        mock_restore.side_effect = ValueError("Page 'public-page' is not pending deletion")
        resp = client.post("/pages/public-page/restore", headers=AUTH)
        assert resp.status_code == 400

    @patch("api.page_storage.get_page")
    def test_restore_page_not_owner(self, mock_get, other_client):
        mock_get.return_value = PUBLIC_PAGE
        resp = other_client.post("/pages/public-page/restore", headers=AUTH)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Per-page timezone support
# ---------------------------------------------------------------------------

PAGE_WITH_TZ = Page(
    slug="tz-page", title="TZ Page", visibility="public",
    owner_uids=[OWNER_UID], timezone="America/Chicago",
)


class TestPageTimezone:
    @patch("api.page_storage.create_page")
    def test_create_page_with_timezone(self, mock_create, client):
        mock_create.return_value = PAGE_WITH_TZ
        resp = client.post("/pages", json={
            "slug": "tz-page", "title": "TZ Page",
            "timezone": "America/Chicago",
        }, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["page"]["timezone"] == "America/Chicago"

    def test_create_page_invalid_timezone_returns_400(self, client):
        resp = client.post("/pages", json={
            "slug": "bad-tz", "title": "Bad TZ",
            "timezone": "Not/A/Timezone",
        }, headers=AUTH)
        assert resp.status_code == 400
        assert "Invalid timezone" in resp.json()["detail"]

    @patch("api.page_storage.write_audit_log")
    @patch("api.page_storage.update_page")
    @patch("api.page_storage.get_page")
    def test_update_page_timezone(self, mock_get, mock_update, mock_audit, client):
        mock_get.return_value = PUBLIC_PAGE
        updated = Page(
            slug="public-page", title="Public", visibility="public",
            owner_uids=[OWNER_UID], timezone="Europe/London",
        )
        mock_update.return_value = updated
        resp = client.patch("/pages/public-page",
                            json={"timezone": "Europe/London"}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["page"]["timezone"] == "Europe/London"

    @patch("api.page_storage.get_page")
    def test_update_page_invalid_timezone_returns_400(self, mock_get, client):
        mock_get.return_value = PUBLIC_PAGE
        resp = client.patch("/pages/public-page",
                            json={"timezone": "Fake/Zone"}, headers=AUTH)
        assert resp.status_code == 400
        assert "Invalid timezone" in resp.json()["detail"]

    @patch("api.commit_memory_firestore")
    @patch("api.page_storage.get_page")
    def test_create_memory_uses_page_timezone(self, mock_get, mock_commit, client):
        """POST /pages/{slug}/memories should resolve today using the page's timezone."""
        mock_get.return_value = PAGE_WITH_TZ
        mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Test", title="Meeting", page_id="tz-page",
        )
        mock_commit.return_value = [CommitResult(action="created", doc_id="m1", memory=mem)]
        resp = client.post("/pages/tz-page/memories",
                           json={"message": "Meeting"}, headers=AUTH)
        assert resp.status_code == 200
        call_kwargs = mock_commit.call_args[1]
        assert "today" in call_kwargs

    @patch("api.firestore_storage.load_memories_by_page")
    @patch("api.page_storage.get_page")
    def test_list_memories_uses_page_timezone(self, mock_get, mock_load):
        """GET /pages/{slug}/memories should resolve today using the page's timezone."""
        mock_get.return_value = PAGE_WITH_TZ
        mock_load.return_value = []
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/tz-page/memories")
        assert resp.status_code == 200
        mock_load.assert_called_once()

    @patch("api.commit_memory_firestore")
    @patch("api.page_storage.get_page")
    def test_create_memory_no_timezone_uses_legacy(self, mock_get, mock_commit, client):
        """Page without timezone should fall back to America/New_York via resolve_tz."""
        mock_get.return_value = PUBLIC_PAGE  # timezone=None
        mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Test", title="Event", page_id="public-page",
        )
        mock_commit.return_value = [CommitResult(action="created", doc_id="m1", memory=mem)]
        resp = client.post("/pages/public-page/memories",
                           json={"message": "Event"}, headers=AUTH)
        assert resp.status_code == 200
        call_kwargs = mock_commit.call_args[1]
        assert "today" in call_kwargs


# ---------------------------------------------------------------------------
# Member role — list memories
# ---------------------------------------------------------------------------

class TestMemberRole:
    @patch("api.firestore_storage.load_memories_by_page")
    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_member_sees_public_and_members_events_on_public_page(
        self, mock_get, mock_verify, mock_load
    ):
        """Members can see public and members-only events on public pages."""
        mock_get.return_value = PUBLIC_PAGE_WITH_MEMBER
        mock_verify.return_value = {"uid": MEMBER_UID}
        public_mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Public event", page_id="public-page", visibility="public",
        )
        members_mem = Memory(
            target=date(2026, 3, 6), expires=date(2026, 4, 5),
            content="Members event", page_id="public-page", visibility="members",
        )
        mock_load.return_value = [("m1", public_mem), ("m2", members_mem)]
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/public-page/memories", headers=AUTH)
        assert resp.status_code == 200
        memories = resp.json()["memories"]
        assert len(memories) == 2
        ids = {m["id"] for m in memories}
        assert ids == {"m1", "m2"}

    @patch("api.firestore_storage.load_memories_by_page")
    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_non_member_still_hidden_from_members_events(
        self, mock_get, mock_verify, mock_load
    ):
        """Non-members only see public events, even when authenticated."""
        mock_get.return_value = PUBLIC_PAGE_WITH_MEMBER
        mock_verify.return_value = {"uid": OTHER_UID}
        public_mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Public event", page_id="public-page", visibility="public",
        )
        members_mem = Memory(
            target=date(2026, 3, 6), expires=date(2026, 4, 5),
            content="Members event", page_id="public-page", visibility="members",
        )
        mock_load.return_value = [("m1", public_mem), ("m2", members_mem)]
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/public-page/memories", headers=AUTH)
        assert resp.status_code == 200
        memories = resp.json()["memories"]
        assert len(memories) == 1
        assert memories[0]["id"] == "m1"

    @patch("api.firestore_storage.load_memories_by_page")
    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_member_can_read_personal_page_memories(
        self, mock_get, mock_verify, mock_load
    ):
        """Members can read personal page memories (public + members-only)."""
        mock_get.return_value = PERSONAL_PAGE_WITH_MEMBER
        mock_verify.return_value = {"uid": MEMBER_UID}
        public_mem = Memory(
            target=date(2026, 3, 5), expires=date(2026, 4, 4),
            content="Public event", page_id="personal-page", visibility="public",
        )
        members_mem = Memory(
            target=date(2026, 3, 6), expires=date(2026, 4, 5),
            content="Members event", page_id="personal-page", visibility="members",
        )
        mock_load.return_value = [("m1", public_mem), ("m2", members_mem)]
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/personal-page/memories", headers=AUTH)
        assert resp.status_code == 200
        memories = resp.json()["memories"]
        assert len(memories) == 2

    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_non_member_cannot_read_personal_page_memories(
        self, mock_get, mock_verify
    ):
        """Non-members cannot access personal page memories."""
        mock_get.return_value = PERSONAL_PAGE_WITH_MEMBER
        mock_verify.return_value = {"uid": OTHER_UID}
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/personal-page/memories", headers=AUTH)
        assert resp.status_code == 403

    @patch("api._verify_firebase_token")
    @patch("api.page_storage.get_page")
    def test_member_can_get_personal_page_metadata(self, mock_get, mock_verify):
        """Members can read personal page metadata."""
        mock_get.return_value = PERSONAL_PAGE_WITH_MEMBER
        mock_verify.return_value = {"uid": MEMBER_UID}
        from api import app
        c = TestClient(app)
        resp = c.get("/pages/personal-page", headers=AUTH)
        assert resp.status_code == 200

    @patch("api.page_storage.get_page")
    def test_member_cannot_create_memory(self, mock_get, member_client):
        """Members cannot create memories (owner-only)."""
        mock_get.return_value = PUBLIC_PAGE_WITH_MEMBER
        resp = member_client.post("/pages/public-page/memories",
                                  json={"message": "test"}, headers=AUTH)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Member invite flow
# ---------------------------------------------------------------------------

class TestMemberInvite:
    @patch("api.page_storage.write_audit_log")
    @patch("api.page_storage.create_invite")
    @patch("api.page_storage.get_page")
    def test_owner_can_create_member_invite(self, mock_get, mock_create, mock_audit, client):
        mock_get.return_value = PUBLIC_PAGE
        mock_create.return_value = Invite(
            invite_id="inv-member", page_slug="public-page",
            created_by=OWNER_UID, role="member",
        )
        resp = client.post("/pages/public-page/invites",
                           json={"role": "member"}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["invite"]["invite_id"] == "inv-member"
        assert data["invite"]["role"] == "member"
        mock_create.assert_called_once_with("public-page", OWNER_UID, role="member")

    @patch("api.page_storage.write_audit_log")
    @patch("api.page_storage.create_invite")
    @patch("api.page_storage.get_page")
    def test_create_invite_default_role_is_owner(self, mock_get, mock_create, mock_audit, client):
        mock_get.return_value = PUBLIC_PAGE
        mock_create.return_value = Invite(
            invite_id="inv-owner", page_slug="public-page",
            created_by=OWNER_UID, role="owner",
        )
        resp = client.post("/pages/public-page/invites", headers=AUTH)
        assert resp.status_code == 200
        mock_create.assert_called_once_with("public-page", OWNER_UID, role="owner")

    @patch("api.page_storage.create_invite")
    @patch("api.page_storage.get_page")
    def test_create_invite_invalid_role_returns_400(self, mock_get, mock_create, client):
        mock_get.return_value = PUBLIC_PAGE
        mock_create.side_effect = ValueError("role must be 'owner' or 'member'")
        resp = client.post("/pages/public-page/invites",
                           json={"role": "admin"}, headers=AUTH)
        assert resp.status_code == 400


