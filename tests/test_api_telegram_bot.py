"""Integration tests for the Telegram bot API endpoints in api_v2.py.

Tests bot registration, config management, link code generation,
and webhook handling using FastAPI TestClient with mocked Firestore
and Telegram API calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from models import Room, TelegramBotConfig, TelegramUserLink

ORGANIZER_UID = "uid-organizer"
PARTICIPANT_UID = "uid-participant"
AUTH = {"Authorization": "Bearer fake-token"}


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


def _make_room(**kwargs) -> Room:
    defaults = dict(
        room_id="rm-1",
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
    return Room(**defaults)


def _make_bot_config(**kwargs) -> TelegramBotConfig:
    defaults = dict(
        bot_id="123456",
        room_id="rm-1",
        bot_token="fake-bot-token",
        bot_username="TestBot",
        webhook_secret="secret-abc",
        mode="read_only",
        created_by=ORGANIZER_UID,
    )
    defaults.update(kwargs)
    return TelegramBotConfig(**defaults)


# ---------------------------------------------------------------------------
# POST /rooms/{room_id}/telegram-bot (register)
# ---------------------------------------------------------------------------

class TestRegisterTelegramBot:
    def test_register_success(self, organizer_client):
        rm = _make_room()
        mock_get_me_resp = MagicMock()
        mock_get_me_resp.status_code = 200
        mock_get_me_resp.json.return_value = {
            "ok": True,
            "result": {"id": 123456, "username": "TestBot"},
        }
        mock_set_webhook_resp = MagicMock()
        mock_set_webhook_resp.status_code = 200
        mock_set_webhook_resp.json.return_value = {"ok": True}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_get_me_resp)
        mock_client.post = AsyncMock(return_value=mock_set_webhook_resp)

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=None),
            patch("api_v2.telegram_storage.save_bot_config"),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {"WEBHOOK_BASE_URL": "https://example.com"}),
        ):
            resp = organizer_client.post(
                "/v2/rooms/rm-1/telegram-bot",
                json={"bot_token": "fake-token", "mode": "read_only"},
                headers=AUTH,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["bot_id"] == "123456"
        assert data["bot_username"] == "TestBot"
        assert "bot_token" not in data

    def test_register_uses_app_base_url_fallback(self, organizer_client):
        rm = _make_room()
        mock_get_me_resp = MagicMock()
        mock_get_me_resp.status_code = 200
        mock_get_me_resp.json.return_value = {
            "ok": True,
            "result": {"id": 123456, "username": "TestBot"},
        }
        mock_set_webhook_resp = MagicMock()
        mock_set_webhook_resp.status_code = 200
        mock_set_webhook_resp.json.return_value = {"ok": True}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_get_me_resp)
        mock_client.post = AsyncMock(return_value=mock_set_webhook_resp)

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=None),
            patch("api_v2.telegram_storage.save_bot_config"),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {"APP_BASE_URL": "https://app.example.com"}, clear=True),
        ):
            resp = organizer_client.post(
                "/v2/rooms/rm-1/telegram-bot",
                json={"bot_token": "fake-token", "mode": "read_only"},
                headers=AUTH,
            )

        assert resp.status_code == 201
        _, kwargs = mock_client.post.await_args
        assert kwargs["json"]["url"] == "https://app.example.com/v2/channels/telegram/webhook/123456"

    def test_register_uses_https_request_origin_when_env_missing(self):
        from api import app
        from api_v2 import _require_token

        app.dependency_overrides[_require_token] = _fake_verify(ORGANIZER_UID)
        client = TestClient(app, base_url="https://small-group.ai")

        rm = _make_room()
        mock_get_me_resp = MagicMock()
        mock_get_me_resp.status_code = 200
        mock_get_me_resp.json.return_value = {
            "ok": True,
            "result": {"id": 123456, "username": "TestBot"},
        }
        mock_set_webhook_resp = MagicMock()
        mock_set_webhook_resp.status_code = 200
        mock_set_webhook_resp.json.return_value = {"ok": True}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_get_me_resp)
        mock_client.post = AsyncMock(return_value=mock_set_webhook_resp)

        try:
            with (
                patch("api_v2.room_storage.get_room", return_value=rm),
                patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=None),
                patch("api_v2.telegram_storage.save_bot_config"),
                patch("httpx.AsyncClient", return_value=mock_client),
                patch.dict("os.environ", {}, clear=True),
            ):
                resp = client.post(
                    "/v2/rooms/rm-1/telegram-bot",
                    json={"bot_token": "fake-token", "mode": "read_only"},
                    headers=AUTH,
                )
        finally:
            app.dependency_overrides.clear()
            client.close()

        assert resp.status_code == 201
        _, kwargs = mock_client.post.await_args
        assert kwargs["json"]["url"] == "https://small-group.ai/v2/channels/telegram/webhook/123456"

    def test_register_requires_public_https_base_url(self, organizer_client):
        rm = _make_room()
        mock_get_me_resp = MagicMock()
        mock_get_me_resp.status_code = 200
        mock_get_me_resp.json.return_value = {
            "ok": True,
            "result": {"id": 123456, "username": "TestBot"},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_get_me_resp)

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=None),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.dict("os.environ", {}, clear=True),
        ):
            resp = organizer_client.post(
                "/v2/rooms/rm-1/telegram-bot",
                json={"bot_token": "fake-token", "mode": "read_only"},
                headers=AUTH,
            )

        assert resp.status_code == 503
        assert "public https base url" in resp.json()["detail"].lower()

    def test_register_bot_already_exists(self, organizer_client):
        rm = _make_room()
        existing = _make_bot_config()

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=existing),
        ):
            resp = organizer_client.post(
                "/v2/rooms/rm-1/telegram-bot",
                json={"bot_token": "fake-token"},
                headers=AUTH,
            )

        assert resp.status_code == 409

    def test_register_non_organizer_rejected(self, participant_client):
        rm = _make_room()

        with patch("api_v2.room_storage.get_room", return_value=rm):
            resp = participant_client.post(
                "/v2/rooms/rm-1/telegram-bot",
                json={"bot_token": "fake-token"},
                headers=AUTH,
            )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /rooms/{room_id}/telegram-bot
# ---------------------------------------------------------------------------

class TestGetTelegramBot:
    def test_get_bot_exists(self, organizer_client):
        rm = _make_room()
        config = _make_bot_config()

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=config),
        ):
            resp = organizer_client.get("/v2/rooms/rm-1/telegram-bot", headers=AUTH)

        assert resp.status_code == 200
        data = resp.json()
        assert data["bot_id"] == "123456"
        assert "bot_token" not in data

    def test_get_bot_not_found(self, organizer_client):
        rm = _make_room()

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=None),
        ):
            resp = organizer_client.get("/v2/rooms/rm-1/telegram-bot", headers=AUTH)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /rooms/{room_id}/telegram-bot
# ---------------------------------------------------------------------------

class TestUpdateTelegramBot:
    def test_update_mode(self, organizer_client):
        rm = _make_room()
        config = _make_bot_config(mode="read_only")

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=config),
            patch("api_v2.telegram_storage.save_bot_config"),
        ):
            resp = organizer_client.patch(
                "/v2/rooms/rm-1/telegram-bot",
                json={"mode": "read_write"},
                headers=AUTH,
            )

        assert resp.status_code == 200
        assert resp.json()["mode"] == "read_write"

    def test_update_invalid_mode(self, organizer_client):
        rm = _make_room()
        config = _make_bot_config()

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=config),
        ):
            resp = organizer_client.patch(
                "/v2/rooms/rm-1/telegram-bot",
                json={"mode": "invalid"},
                headers=AUTH,
            )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /rooms/{room_id}/telegram-bot
# ---------------------------------------------------------------------------

class TestDeleteTelegramBot:
    def test_delete_success(self, organizer_client):
        rm = _make_room()
        config = _make_bot_config()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=config),
            patch("api_v2.telegram_storage.delete_links_for_bot"),
            patch("api_v2.telegram_storage.delete_bot_config"),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            resp = organizer_client.delete("/v2/rooms/rm-1/telegram-bot", headers=AUTH)

        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_not_found(self, organizer_client):
        rm = _make_room()

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=None),
        ):
            resp = organizer_client.delete("/v2/rooms/rm-1/telegram-bot", headers=AUTH)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /rooms/{room_id}/telegram-bot/link-code
# ---------------------------------------------------------------------------

class TestGenerateLinkCode:
    def test_generate_code(self, organizer_client):
        rm = _make_room()
        config = _make_bot_config()

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=config),
            patch("api_v2.telegram_storage.save_link_code"),
        ):
            resp = organizer_client.post(
                "/v2/rooms/rm-1/telegram-bot/link-code",
                headers=AUTH,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert "code" in data
        assert len(data["code"]) == 6
        assert data["expires_in"] == 300

    def test_generate_code_no_bot(self, organizer_client):
        rm = _make_room()

        with (
            patch("api_v2.room_storage.get_room", return_value=rm),
            patch("api_v2.telegram_storage.get_bot_config_for_room", return_value=None),
        ):
            resp = organizer_client.post(
                "/v2/rooms/rm-1/telegram-bot/link-code",
                headers=AUTH,
            )

        assert resp.status_code == 404

    def test_generate_code_non_organizer(self, participant_client):
        rm = _make_room()

        with patch("api_v2.room_storage.get_room", return_value=rm):
            resp = participant_client.post(
                "/v2/rooms/rm-1/telegram-bot/link-code",
                headers=AUTH,
            )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

class TestWebhookEndpoint:
    def _webhook_url(self, bot_id="123456"):
        return f"/v2/channels/telegram/webhook/{bot_id}"

    def test_webhook_valid_start_command(self, organizer_client):
        config = _make_bot_config()

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2._send_telegram_message", new_callable=AsyncMock) as mock_send,
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "message": {
                        "from": {"id": 999, "first_name": "Alice"},
                        "chat": {"id": 100},
                        "text": "/start",
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        mock_send.assert_called_once()
        assert "welcome" in mock_send.call_args[0][2].lower()

    def test_webhook_group_chat_is_rejected(self, organizer_client):
        config = _make_bot_config()

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2._send_telegram_message", new_callable=AsyncMock) as mock_send,
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "message": {
                        "from": {"id": 999, "first_name": "Alice"},
                        "chat": {"id": -100, "type": "group"},
                        "text": "/start",
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        assert "private chats only" in mock_send.call_args[0][2].lower()

    def test_webhook_invalid_secret(self, organizer_client):
        config = _make_bot_config()

        with patch("api_v2.telegram_storage.get_bot_config", return_value=config):
            resp = organizer_client.post(
                self._webhook_url(),
                json={"message": {"from": {"id": 1}, "chat": {"id": 1}, "text": "hi"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
            )

        assert resp.status_code == 403

    def test_webhook_unknown_bot(self, organizer_client):
        with patch("api_v2.telegram_storage.get_bot_config", return_value=None):
            resp = organizer_client.post(
                self._webhook_url("unknown-bot"),
                json={"message": {"from": {"id": 1}, "chat": {"id": 1}, "text": "hi"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "anything"},
            )

        assert resp.status_code == 404

    def test_webhook_link_command_valid(self, organizer_client):
        config = _make_bot_config()

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2.telegram_storage.get_and_consume_link_code", return_value={
                "room_id": "rm-1", "app_uid": "uid-organizer",
            }),
            patch("api_v2.telegram_storage.save_telegram_link"),
            patch("api_v2._send_telegram_message", new_callable=AsyncMock) as mock_send,
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "message": {
                        "from": {"id": 999, "first_name": "Alice", "last_name": "Smith"},
                        "chat": {"id": 100},
                        "text": "/link ABC123",
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        assert "linked" in mock_send.call_args[0][2].lower()

    def test_webhook_link_command_rejects_other_room_code(self, organizer_client):
        config = _make_bot_config(room_id="rm-1")

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2.telegram_storage.get_and_consume_link_code", return_value={
                "room_id": "rm-2", "app_uid": "uid-organizer",
            }),
            patch("api_v2.telegram_storage.save_telegram_link") as mock_save,
            patch("api_v2._send_telegram_message", new_callable=AsyncMock) as mock_send,
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "message": {
                        "from": {"id": 999, "first_name": "Alice"},
                        "chat": {"id": 100},
                        "text": "/link ABC123",
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        assert "different room" in mock_send.call_args[0][2].lower()
        mock_save.assert_not_called()

    def test_webhook_link_command_invalid_code(self, organizer_client):
        config = _make_bot_config()

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2.telegram_storage.get_and_consume_link_code", return_value=None),
            patch("api_v2._send_telegram_message", new_callable=AsyncMock) as mock_send,
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "message": {
                        "from": {"id": 999, "first_name": "Alice"},
                        "chat": {"id": 100},
                        "text": "/link BADCODE",
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        assert "invalid" in mock_send.call_args[0][2].lower()

    def test_webhook_unlinked_user_message(self, organizer_client):
        config = _make_bot_config()

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2.telegram_storage.get_link_by_telegram_user_for_room", return_value=None),
            patch("api_v2._send_telegram_message", new_callable=AsyncMock) as mock_send,
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "message": {
                        "from": {"id": 999, "first_name": "Bob"},
                        "chat": {"id": 100},
                        "text": "When is the next meeting?",
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        assert "link your account" in mock_send.call_args[0][2].lower()

    def test_webhook_linked_user_routes_to_handler(self, organizer_client):
        config = _make_bot_config()
        link = TelegramUserLink(
            telegram_user_id="999", app_uid="uid-organizer", display_name="Alice",
        )

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2.telegram_storage.get_link_by_telegram_user_for_room", return_value=link),
            patch("telegram_chat_handler.handle_telegram_message", new_callable=AsyncMock) as mock_handler,
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "message": {
                        "from": {"id": 999, "first_name": "Alice"},
                        "chat": {"id": 100},
                        "text": "Reschedule tomorrow",
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        mock_handler.assert_called_once()
        call_kwargs = mock_handler.call_args[1]
        assert call_kwargs["app_uid"] == "uid-organizer"
        assert call_kwargs["text"] == "Reschedule tomorrow"

    def test_webhook_callback_query(self, organizer_client):
        config = _make_bot_config()
        link = TelegramUserLink(
            telegram_user_id="999", app_uid="uid-organizer", display_name="Alice",
        )

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2.telegram_storage.get_link_by_telegram_user_for_room", return_value=link),
            patch("telegram_chat_handler.handle_telegram_callback", new_callable=AsyncMock) as mock_cb,
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "callback_query": {
                        "id": "cb-1",
                        "from": {"id": 999},
                        "data": "confirm:act-1",
                        "message": {"message_id": 42, "chat": {"id": 100}},
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        mock_cb.assert_called_once()

    def test_webhook_callback_query_unlinked_user(self, organizer_client):
        config = _make_bot_config()

        with (
            patch("api_v2.telegram_storage.get_bot_config", return_value=config),
            patch("api_v2.telegram_storage.get_link_by_telegram_user_for_room", return_value=None),
        ):
            resp = organizer_client.post(
                self._webhook_url(),
                json={
                    "callback_query": {
                        "id": "cb-1",
                        "from": {"id": 999},
                        "data": "confirm:act-1",
                        "message": {"message_id": 42, "chat": {"id": 100}},
                    }
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        # Should return ok but not process (no handler called)
        assert resp.status_code == 200

    def test_webhook_no_message_or_callback(self, organizer_client):
        config = _make_bot_config()

        with patch("api_v2.telegram_storage.get_bot_config", return_value=config):
            resp = organizer_client.post(
                self._webhook_url(),
                json={"update_id": 12345},
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-abc"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
