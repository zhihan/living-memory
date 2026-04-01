"""Tests for telegram_chat_handler.py — message handling and callback queries."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import (
    ChatSession,
    ChatTurn,
    Room,
    TelegramBotConfig,
    TelegramUserLink,
)


def _utcnow():
    return datetime.now(timezone.utc)


def _make_bot_config(mode="read_write", **kwargs) -> TelegramBotConfig:
    defaults = dict(
        bot_id="123456",
        room_id="rm-1",
        bot_token="fake-token",
        bot_username="TestBot",
        webhook_secret="secret-123",
        mode=mode,
        created_by="uid-organizer",
    )
    defaults.update(kwargs)
    return TelegramBotConfig(**defaults)


def _make_room(**kwargs) -> Room:
    defaults = dict(
        room_id="rm-1",
        title="Standups",
        type="shared",
        timezone="UTC",
        owner_uids=["uid-organizer"],
        member_roles={"uid-organizer": "organizer"},
    )
    defaults.update(kwargs)
    return Room(**defaults)


def _make_session(**kwargs) -> ChatSession:
    defaults = dict(
        session_id="sess-1",
        room_id="rm-1",
        telegram_chat_id="chat-100",
        app_uid="uid-organizer",
        turns=[],
    )
    defaults.update(kwargs)
    return ChatSession(**defaults)


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# handle_telegram_message
# ---------------------------------------------------------------------------

class TestHandleTelegramMessage:
    def test_basic_message(self):
        """A linked organizer sends a message and gets an AI response."""
        bot_config = _make_bot_config()
        session = _make_session()

        with (
            patch("telegram_chat_handler.telegram_storage") as mock_storage,
            patch("telegram_chat_handler.room_storage") as mock_room_storage,
            patch("telegram_chat_handler.series_storage") as mock_series_storage,
            patch("telegram_chat_handler.run_assistant_stream") as mock_stream,
            patch("telegram_chat_handler._send_telegram_message", new_callable=AsyncMock) as mock_send,
            patch("telegram_chat_handler._send_telegram_message_with_inline_keyboard", new_callable=AsyncMock),
        ):
            mock_storage.get_or_create_session.return_value = session
            mock_storage.get_recent_turns.return_value = []
            mock_room_storage.get_room.return_value = _make_room()
            mock_series_storage.list_series_for_room.return_value = []
            mock_series_storage.list_occurrences_for_room.return_value = []
            mock_stream.return_value = iter([
                {"type": "text_chunk", "text": "Your next meeting is tomorrow."},
                {"type": "done"},
            ])

            from telegram_chat_handler import handle_telegram_message
            _run(handle_telegram_message(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                chat_id="chat-100",
                text="When is my next meeting?",
            ))

        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][2]
        assert "tomorrow" in sent_text
        assert mock_storage.append_turn.call_count == 2

    def test_input_length_cap(self):
        """Messages over 2000 chars should be rejected."""
        bot_config = _make_bot_config()
        long_text = "x" * 2001

        with patch("telegram_chat_handler._send_telegram_message", new_callable=AsyncMock) as mock_send:
            from telegram_chat_handler import handle_telegram_message
            _run(handle_telegram_message(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                chat_id="chat-100",
                text=long_text,
            ))

        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][2]
        assert "too long" in sent_text.lower()

    def test_read_only_strips_actions(self):
        """In read_only mode, action proposals should be discarded."""
        bot_config = _make_bot_config(mode="read_only")
        session = _make_session()

        with (
            patch("telegram_chat_handler.telegram_storage") as mock_storage,
            patch("telegram_chat_handler.room_storage") as mock_room_storage,
            patch("telegram_chat_handler.series_storage") as mock_series_storage,
            patch("telegram_chat_handler.run_assistant_stream") as mock_stream,
            patch("telegram_chat_handler._send_telegram_message", new_callable=AsyncMock) as mock_send,
            patch("telegram_chat_handler._send_telegram_message_with_inline_keyboard", new_callable=AsyncMock) as mock_send_kb,
        ):
            mock_storage.get_or_create_session.return_value = session
            mock_storage.get_recent_turns.return_value = []
            mock_room_storage.get_room.return_value = _make_room()
            mock_series_storage.list_series_for_room.return_value = []
            mock_series_storage.list_occurrences_for_room.return_value = []
            mock_stream.return_value = iter([
                {"type": "text_chunk", "text": "I'll create that series."},
                {"type": "action_proposal", "action_id": "act-1",
                 "action_type": "create_series", "preview_summary": "Create weekly standup",
                 "payload": {}},
                {"type": "done"},
            ])

            from telegram_chat_handler import handle_telegram_message
            _run(handle_telegram_message(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                chat_id="chat-100",
                text="Create a weekly standup",
            ))

        mock_send.assert_called_once()
        mock_send_kb.assert_not_called()

    def test_read_write_sends_inline_buttons(self):
        """In read_write mode, action proposals should send inline keyboard."""
        bot_config = _make_bot_config(mode="read_write")
        session = _make_session()

        with (
            patch("telegram_chat_handler.telegram_storage") as mock_storage,
            patch("telegram_chat_handler.room_storage") as mock_room_storage,
            patch("telegram_chat_handler.series_storage") as mock_series_storage,
            patch("telegram_chat_handler.run_assistant_stream") as mock_stream,
            patch("telegram_chat_handler._send_telegram_message", new_callable=AsyncMock) as mock_send,
            patch("telegram_chat_handler._send_telegram_message_with_inline_keyboard", new_callable=AsyncMock) as mock_send_kb,
        ):
            mock_storage.get_or_create_session.return_value = session
            mock_storage.get_recent_turns.return_value = []
            mock_room_storage.get_room.return_value = _make_room()
            mock_series_storage.list_series_for_room.return_value = []
            mock_series_storage.list_occurrences_for_room.return_value = []
            mock_stream.return_value = iter([
                {"type": "text_chunk", "text": "I'll create that."},
                {"type": "action_proposal", "action_id": "act-1",
                 "action_type": "create_series",
                 "preview_summary": "Create weekly standup",
                 "payload": {}},
                {"type": "done"},
            ])

            from telegram_chat_handler import handle_telegram_message
            _run(handle_telegram_message(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                chat_id="chat-100",
                text="Create a weekly standup",
            ))

        mock_send.assert_called_once()
        mock_send_kb.assert_called_once()
        kb_args = mock_send_kb.call_args
        reply_markup = kb_args[0][3]
        buttons = reply_markup["inline_keyboard"][0]
        assert len(buttons) == 2
        assert "confirm:act-1" in buttons[0]["callback_data"]
        assert "cancel:act-1" in buttons[1]["callback_data"]

    def test_assistant_error_fallback(self):
        """If the assistant stream raises, the handler should send an error message."""
        bot_config = _make_bot_config()
        session = _make_session()

        with (
            patch("telegram_chat_handler.telegram_storage") as mock_storage,
            patch("telegram_chat_handler.room_storage") as mock_room_storage,
            patch("telegram_chat_handler.series_storage") as mock_series_storage,
            patch("telegram_chat_handler.run_assistant_stream", side_effect=RuntimeError("AI broke")),
            patch("telegram_chat_handler._send_telegram_message", new_callable=AsyncMock) as mock_send,
            patch("telegram_chat_handler._send_telegram_message_with_inline_keyboard", new_callable=AsyncMock),
        ):
            mock_storage.get_or_create_session.return_value = session
            mock_storage.get_recent_turns.return_value = []
            mock_room_storage.get_room.return_value = _make_room()
            mock_series_storage.list_series_for_room.return_value = []
            mock_series_storage.list_occurrences_for_room.return_value = []

            from telegram_chat_handler import handle_telegram_message
            _run(handle_telegram_message(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                chat_id="chat-100",
                text="Hello",
            ))

        mock_send.assert_called_once()
        assert "wrong" in mock_send.call_args[0][2].lower()

    def test_room_context_uses_bot_room_id(self):
        """The handler should use bot_config.room_id, not user-supplied data."""
        bot_config = _make_bot_config(room_id="rm-correct")
        session = _make_session(room_id="rm-correct")

        with (
            patch("telegram_chat_handler.telegram_storage") as mock_storage,
            patch("telegram_chat_handler.room_storage") as mock_room_storage,
            patch("telegram_chat_handler.series_storage") as mock_series_storage,
            patch("telegram_chat_handler.run_assistant_stream") as mock_stream,
            patch("telegram_chat_handler._send_telegram_message", new_callable=AsyncMock),
            patch("telegram_chat_handler._send_telegram_message_with_inline_keyboard", new_callable=AsyncMock),
        ):
            mock_storage.get_or_create_session.return_value = session
            mock_storage.get_recent_turns.return_value = []
            mock_room_storage.get_room.return_value = _make_room(room_id="rm-correct")
            mock_series_storage.list_series_for_room.return_value = []
            mock_series_storage.list_occurrences_for_room.return_value = []
            mock_stream.return_value = iter([
                {"type": "text_chunk", "text": "ok"},
                {"type": "done"},
            ])

            from telegram_chat_handler import handle_telegram_message
            _run(handle_telegram_message(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                chat_id="chat-100",
                text="test",
            ))

        mock_room_storage.get_room.assert_called_with("rm-correct")
        call_kwargs = mock_stream.call_args
        assert call_kwargs[1]["room_id"] == "rm-correct"


# ---------------------------------------------------------------------------
# handle_telegram_callback
# ---------------------------------------------------------------------------

class TestHandleTelegramCallback:
    def _make_pending_action(self, room_id="rm-1", uid="uid-organizer", status="pending"):
        from assistant_actions import PendingAction
        return PendingAction(
            action_id="act-1",
            room_id=room_id,
            requested_by_uid=uid,
            action_type="draft_material",
            preview_summary="Draft meeting agenda",
            payload={"title": "Agenda", "material_kind": "agenda", "draft_text": "Items"},
            status=status,
        )

    def _make_callback_query(self, action="confirm", action_id="act-1"):
        return {
            "id": "cb-query-1",
            "from": {"id": 12345},
            "data": f"{action}:{action_id}",
            "message": {
                "message_id": 42,
                "chat": {"id": 100},
            },
        }

    def test_confirm_action(self):
        bot_config = _make_bot_config()
        pending = self._make_pending_action()

        with (
            patch("telegram_chat_handler.get_pending_action", return_value=pending),
            patch("telegram_chat_handler.execute_action", return_value={"ok": True}),
            patch("telegram_chat_handler.update_pending_action_status") as mock_update,
            patch("telegram_chat_handler._edit_telegram_message", new_callable=AsyncMock) as mock_edit,
            patch("telegram_chat_handler._answer_callback_query", new_callable=AsyncMock) as mock_answer,
            patch("telegram_chat_handler.telegram_storage") as mock_storage,
        ):
            mock_storage.get_or_create_session.return_value = _make_session()

            from telegram_chat_handler import handle_telegram_callback
            _run(handle_telegram_callback(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                callback_query=self._make_callback_query("confirm", "act-1"),
            ))

        assert mock_update.call_count == 2
        mock_update.assert_any_call("act-1", "confirmed")
        mock_edit.assert_called_once()
        assert "\u2705" in mock_edit.call_args[0][3]
        mock_answer.assert_called_once()
        mock_storage.append_turn.assert_called_once()

    def test_cancel_action(self):
        bot_config = _make_bot_config()
        pending = self._make_pending_action()

        with (
            patch("telegram_chat_handler.get_pending_action", return_value=pending),
            patch("telegram_chat_handler.update_pending_action_status") as mock_update,
            patch("telegram_chat_handler._edit_telegram_message", new_callable=AsyncMock) as mock_edit,
            patch("telegram_chat_handler._answer_callback_query", new_callable=AsyncMock) as mock_answer,
            patch("telegram_chat_handler.telegram_storage") as mock_storage,
        ):
            mock_storage.get_or_create_session.return_value = _make_session()

            from telegram_chat_handler import handle_telegram_callback
            _run(handle_telegram_callback(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                callback_query=self._make_callback_query("cancel", "act-1"),
            ))

        mock_update.assert_called_once_with("act-1", "cancelled")
        mock_edit.assert_called_once()
        assert "\u274c" in mock_edit.call_args[0][3]
        mock_answer.assert_called_once()

    def test_action_not_found(self):
        bot_config = _make_bot_config()

        with (
            patch("telegram_chat_handler.get_pending_action", return_value=None),
            patch("telegram_chat_handler._edit_telegram_message", new_callable=AsyncMock) as mock_edit,
            patch("telegram_chat_handler._answer_callback_query", new_callable=AsyncMock) as mock_answer,
        ):
            from telegram_chat_handler import handle_telegram_callback
            _run(handle_telegram_callback(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                callback_query=self._make_callback_query("confirm", "missing-id"),
            ))

        assert "not found" in mock_edit.call_args[0][3].lower()
        mock_answer.assert_called_once()

    def test_wrong_room(self):
        bot_config = _make_bot_config(room_id="rm-1")
        pending = self._make_pending_action(room_id="rm-other")

        with (
            patch("telegram_chat_handler.get_pending_action", return_value=pending),
            patch("telegram_chat_handler._edit_telegram_message", new_callable=AsyncMock) as mock_edit,
            patch("telegram_chat_handler._answer_callback_query", new_callable=AsyncMock),
        ):
            from telegram_chat_handler import handle_telegram_callback
            _run(handle_telegram_callback(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                callback_query=self._make_callback_query("confirm", "act-1"),
            ))

        assert "does not belong" in mock_edit.call_args[0][3].lower()

    def test_wrong_user(self):
        bot_config = _make_bot_config()
        pending = self._make_pending_action(uid="uid-someone-else")

        with (
            patch("telegram_chat_handler.get_pending_action", return_value=pending),
            patch("telegram_chat_handler._edit_telegram_message", new_callable=AsyncMock) as mock_edit,
            patch("telegram_chat_handler._answer_callback_query", new_callable=AsyncMock),
        ):
            from telegram_chat_handler import handle_telegram_callback
            _run(handle_telegram_callback(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                callback_query=self._make_callback_query("confirm", "act-1"),
            ))

        assert "only the user" in mock_edit.call_args[0][3].lower()

    def test_action_already_executed(self):
        bot_config = _make_bot_config()
        pending = self._make_pending_action(status="executed")

        with (
            patch("telegram_chat_handler.get_pending_action", return_value=pending),
            patch("telegram_chat_handler._edit_telegram_message", new_callable=AsyncMock) as mock_edit,
            patch("telegram_chat_handler._answer_callback_query", new_callable=AsyncMock),
        ):
            from telegram_chat_handler import handle_telegram_callback
            _run(handle_telegram_callback(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                callback_query=self._make_callback_query("confirm", "act-1"),
            ))

        assert "already executed" in mock_edit.call_args[0][3].lower()

    def test_execution_failure(self):
        bot_config = _make_bot_config()
        pending = self._make_pending_action()

        with (
            patch("telegram_chat_handler.get_pending_action", return_value=pending),
            patch("telegram_chat_handler.execute_action", side_effect=ValueError("DB error")),
            patch("telegram_chat_handler.update_pending_action_status") as mock_update,
            patch("telegram_chat_handler._edit_telegram_message", new_callable=AsyncMock) as mock_edit,
            patch("telegram_chat_handler._answer_callback_query", new_callable=AsyncMock),
            patch("telegram_chat_handler.telegram_storage") as mock_storage,
        ):
            mock_storage.get_or_create_session.return_value = _make_session()

            from telegram_chat_handler import handle_telegram_callback
            _run(handle_telegram_callback(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                callback_query=self._make_callback_query("confirm", "act-1"),
            ))

        mock_update.assert_any_call("act-1", "failed", error="DB error")
        assert "failed" in mock_edit.call_args[0][3].lower()

    def test_invalid_callback_data(self):
        """Malformed callback_data should be silently dismissed."""
        bot_config = _make_bot_config()
        callback_query = {
            "id": "cb-1",
            "from": {"id": 12345},
            "data": "garbage",
            "message": {"message_id": 42, "chat": {"id": 100}},
        }

        with patch("telegram_chat_handler._answer_callback_query", new_callable=AsyncMock) as mock_answer:
            from telegram_chat_handler import handle_telegram_callback
            _run(handle_telegram_callback(
                bot_config=bot_config,
                telegram_user_id="tg-1",
                app_uid="uid-organizer",
                callback_query=callback_query,
            ))

        mock_answer.assert_called_once()
