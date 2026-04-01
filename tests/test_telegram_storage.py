"""Tests for telegram_storage.py — bot config, user link, link code, and chat session CRUD."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import ChatTurn, ChatSession, TelegramBotConfig, TelegramUserLink


def _utcnow():
    return datetime.now(timezone.utc)


def _make_bot_config(**kwargs) -> TelegramBotConfig:
    defaults = dict(
        bot_id="123456",
        room_id="rm-1",
        bot_token="fake-token",
        bot_username="TestBot",
        webhook_secret="secret-123",
        mode="read_only",
        created_by="uid-organizer",
    )
    defaults.update(kwargs)
    return TelegramBotConfig(**defaults)


def _make_link(**kwargs) -> TelegramUserLink:
    defaults = dict(
        telegram_user_id="tg-user-1",
        app_uid="uid-alice",
        display_name="Alice",
        room_id="rm-1",
        bot_id="123456",
    )
    defaults.update(kwargs)
    return TelegramUserLink(**defaults)


def _mock_db():
    """Create a mock Firestore client. Patch at telegram_storage._get_client."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Bot config CRUD
# ---------------------------------------------------------------------------

class TestBotConfigCRUD:
    def test_save_bot_config(self):
        config = _make_bot_config()
        mock_db = _mock_db()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import save_bot_config
            save_bot_config(config)

        mock_db.collection.assert_called_with("telegram_bots")
        mock_doc_ref.set.assert_called_once()
        assert config.created_at is not None
        assert config.updated_at is not None

    def test_get_bot_config_found(self):
        config = _make_bot_config()
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = config.to_dict()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_bot_config
            result = get_bot_config("123456")

        assert result is not None
        assert result.bot_id == "123456"
        assert result.room_id == "rm-1"

    def test_get_bot_config_not_found(self):
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_bot_config
            result = get_bot_config("nonexistent")

        assert result is None

    def test_get_bot_config_for_room(self):
        config = _make_bot_config()
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = config.to_dict()
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [mock_doc]

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_bot_config_for_room
            result = get_bot_config_for_room("rm-1")

        assert result is not None
        assert result.bot_id == "123456"

    def test_get_bot_config_for_room_not_found(self):
        mock_db = _mock_db()
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_bot_config_for_room
            result = get_bot_config_for_room("rm-missing")

        assert result is None

    def test_delete_bot_config(self):
        mock_db = _mock_db()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import delete_bot_config
            delete_bot_config("123456")

        mock_doc_ref.delete.assert_called_once()

    def test_delete_links_for_bot_only_deletes_matching_room_or_bot(self):
        bot_doc = MagicMock()
        bot_doc.id = "tg-user-1"
        room_doc = MagicMock()
        room_doc.id = "tg-user-2"

        mock_db = _mock_db()
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection

        where_bot = MagicMock()
        where_room = MagicMock()

        def where_side_effect(field, op, value):
            if field == "bot_id":
                where_bot.stream.return_value = [bot_doc]
                return where_bot
            if field == "room_id":
                where_room.stream.return_value = [room_doc]
                return where_room
            raise AssertionError(f"Unexpected query: {field} {op} {value}")

        mock_collection.where.side_effect = where_side_effect

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import delete_links_for_bot
            delete_links_for_bot("123456", "rm-1")

        assert mock_collection.document.call_count == 2
        mock_collection.document.assert_any_call("tg-user-1")
        mock_collection.document.assert_any_call("tg-user-2")


# ---------------------------------------------------------------------------
# User link CRUD
# ---------------------------------------------------------------------------

class TestUserLinkCRUD:
    def test_save_telegram_link(self):
        link = _make_link()
        mock_db = _mock_db()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import save_telegram_link
            save_telegram_link(link)

        mock_db.collection.assert_called_with("telegram_links")
        mock_doc_ref.set.assert_called_once()
        assert link.linked_at is not None

    def test_get_link_by_telegram_user_found(self):
        link = _make_link()
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = link.to_dict()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_link_by_telegram_user
            result = get_link_by_telegram_user("tg-user-1")

        assert result is not None
        assert result.app_uid == "uid-alice"
        assert result.display_name == "Alice"

    def test_get_link_by_telegram_user_not_found(self):
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_link_by_telegram_user
            result = get_link_by_telegram_user("tg-unknown")

        assert result is None

    def test_get_link_by_telegram_user_for_room_found(self):
        link = _make_link(room_id="rm-1")
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = link.to_dict()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_link_by_telegram_user_for_room
            result = get_link_by_telegram_user_for_room("tg-user-1", "rm-1")

        assert result is not None
        assert result.room_id == "rm-1"

    def test_get_link_by_telegram_user_for_room_mismatch(self):
        link = _make_link(room_id="rm-2")
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = link.to_dict()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_link_by_telegram_user_for_room
            result = get_link_by_telegram_user_for_room("tg-user-1", "rm-1")

        assert result is None


# ---------------------------------------------------------------------------
# Link code storage
# ---------------------------------------------------------------------------

class TestLinkCodeStorage:
    def test_save_link_code(self):
        mock_db = _mock_db()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref
        expires = _utcnow() + timedelta(minutes=5)

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import save_link_code
            save_link_code("ABC123", "rm-1", "uid-alice", expires)

        mock_db.collection.assert_called_with("telegram_link_codes")
        saved_data = mock_doc_ref.set.call_args[0][0]
        assert saved_data["code"] == "ABC123"
        assert saved_data["room_id"] == "rm-1"
        assert saved_data["app_uid"] == "uid-alice"

    def test_get_and_consume_link_code_valid(self):
        expires = _utcnow() + timedelta(minutes=5)
        mock_db = _mock_db()
        mock_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "code": "ABC123",
            "room_id": "rm-1",
            "app_uid": "uid-alice",
            "expires_at": expires,
        }
        mock_ref.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_and_consume_link_code
            result = get_and_consume_link_code("ABC123")

        assert result is not None
        assert result["room_id"] == "rm-1"
        assert result["app_uid"] == "uid-alice"
        mock_ref.delete.assert_called_once()

    def test_get_and_consume_link_code_expired(self):
        expires = _utcnow() - timedelta(minutes=1)
        mock_db = _mock_db()
        mock_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "code": "EXPIRED",
            "room_id": "rm-1",
            "app_uid": "uid-alice",
            "expires_at": expires,
        }
        mock_ref.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_and_consume_link_code
            result = get_and_consume_link_code("EXPIRED")

        assert result is None
        mock_ref.delete.assert_called_once()

    def test_get_and_consume_link_code_not_found(self):
        mock_db = _mock_db()
        mock_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_ref.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_and_consume_link_code
            result = get_and_consume_link_code("MISSING")

        assert result is None

    def test_get_and_consume_link_code_iso_string_expiry(self):
        """Expiry stored as ISO string should also work."""
        expires = (_utcnow() + timedelta(minutes=5)).isoformat()
        mock_db = _mock_db()
        mock_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "code": "ISOSTR",
            "room_id": "rm-1",
            "app_uid": "uid-alice",
            "expires_at": expires,
        }
        mock_ref.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_and_consume_link_code
            result = get_and_consume_link_code("ISOSTR")

        assert result is not None


# ---------------------------------------------------------------------------
# Chat session CRUD
# ---------------------------------------------------------------------------

class TestChatSessionCRUD:
    def test_get_or_create_session_creates_new(self):
        mock_db = _mock_db()
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = []
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_or_create_session
            session = get_or_create_session("rm-1", "chat-100", "uid-alice")

        assert session.room_id == "rm-1"
        assert session.telegram_chat_id == "chat-100"
        assert session.app_uid == "uid-alice"
        assert session.turns == []
        mock_doc_ref.set.assert_called_once()

    def test_get_or_create_session_returns_existing(self):
        existing = ChatSession(
            session_id="sess-1",
            room_id="rm-1",
            telegram_chat_id="chat-100",
            app_uid="uid-alice",
            turns=[ChatTurn(role="user", text="Hello")],
        )
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = existing.to_dict()
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = [mock_doc]

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_or_create_session
            session = get_or_create_session("rm-1", "chat-100", "uid-alice")

        assert session.session_id == "sess-1"
        assert len(session.turns) == 1

    def test_append_turn(self):
        import sys

        # Pre-mock the google.cloud.firestore_v1 module so the import inside
        # append_turn succeeds without the real SDK installed.
        mock_fv1 = MagicMock()
        sentinel = object()
        mock_fv1.ArrayUnion = lambda vals: ("__array_union__", vals)
        with patch.dict(sys.modules, {"google.cloud.firestore_v1": mock_fv1, "google.cloud": MagicMock()}):
            mock_db = _mock_db()
            mock_doc_ref = MagicMock()
            mock_db.collection.return_value.document.return_value = mock_doc_ref

            turn = ChatTurn(role="user", text="Hello", timestamp=_utcnow())

            with patch("telegram_storage._get_client", return_value=mock_db):
                from telegram_storage import append_turn
                append_turn("sess-1", turn)

            mock_doc_ref.update.assert_called_once()
            update_data = mock_doc_ref.update.call_args[0][0]
            assert "turns" in update_data
            assert "updated_at" in update_data

    def test_get_recent_turns_all(self):
        turns = [
            ChatTurn(role="user", text=f"msg-{i}", timestamp=_utcnow()).to_dict()
            for i in range(5)
        ]
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"turns": turns}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_recent_turns
            result = get_recent_turns("sess-1", limit=20)

        assert len(result) == 5
        assert result[0].text == "msg-0"

    def test_get_recent_turns_with_limit(self):
        turns = [
            ChatTurn(role="user", text=f"msg-{i}", timestamp=_utcnow()).to_dict()
            for i in range(30)
        ]
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"turns": turns}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_recent_turns
            result = get_recent_turns("sess-1", limit=20)

        assert len(result) == 20
        assert result[0].text == "msg-10"

    def test_get_recent_turns_not_found(self):
        mock_db = _mock_db()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("telegram_storage._get_client", return_value=mock_db):
            from telegram_storage import get_recent_turns
            result = get_recent_turns("sess-missing")

        assert result == []
