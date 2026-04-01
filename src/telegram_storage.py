"""Firestore-backed storage for Telegram bot configurations and user links."""

from __future__ import annotations

from datetime import datetime, timezone

import uuid

from db import get_client as _get_client
from models import ChatSession, ChatTurn, TelegramBotConfig, TelegramUserLink

TELEGRAM_BOTS_COLLECTION = "telegram_bots"
TELEGRAM_LINKS_COLLECTION = "telegram_links"
LINK_CODES_COLLECTION = "telegram_link_codes"
CHAT_SESSIONS_COLLECTION = "chat_sessions"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def save_bot_config(config: TelegramBotConfig) -> None:
    """Save a TelegramBotConfig document. bot_id is the doc ID."""
    db = _get_client()
    now = _utcnow()
    config.created_at = config.created_at or now
    config.updated_at = now
    db.collection(TELEGRAM_BOTS_COLLECTION).document(config.bot_id).set(
        config.to_dict()
    )


def get_bot_config(bot_id: str) -> TelegramBotConfig | None:
    """Fetch a TelegramBotConfig by bot_id. Returns None if not found."""
    db = _get_client()
    doc = db.collection(TELEGRAM_BOTS_COLLECTION).document(bot_id).get()
    if not doc.exists:
        return None
    return TelegramBotConfig.from_dict(doc.to_dict())


def get_bot_config_for_room(room_id: str) -> TelegramBotConfig | None:
    """Fetch the TelegramBotConfig for a room. Returns None if none exists."""
    db = _get_client()
    docs = (
        db.collection(TELEGRAM_BOTS_COLLECTION)
        .where("room_id", "==", room_id)
        .limit(1)
        .stream()
    )
    for doc in docs:
        return TelegramBotConfig.from_dict(doc.to_dict())
    return None


def delete_bot_config(bot_id: str) -> None:
    """Delete a TelegramBotConfig document."""
    db = _get_client()
    db.collection(TELEGRAM_BOTS_COLLECTION).document(bot_id).delete()


# ---------------------------------------------------------------------------
# Telegram user link storage
# ---------------------------------------------------------------------------


def save_telegram_link(link: TelegramUserLink) -> None:
    """Save a TelegramUserLink document. telegram_user_id is the doc ID."""
    db = _get_client()
    link.linked_at = link.linked_at or _utcnow()
    db.collection(TELEGRAM_LINKS_COLLECTION).document(link.telegram_user_id).set(
        link.to_dict()
    )


def get_link_by_telegram_user(telegram_user_id: str) -> TelegramUserLink | None:
    """Fetch a TelegramUserLink by telegram_user_id. Returns None if not found."""
    db = _get_client()
    doc = db.collection(TELEGRAM_LINKS_COLLECTION).document(telegram_user_id).get()
    if not doc.exists:
        return None
    return TelegramUserLink.from_dict(doc.to_dict())


def delete_links_for_bot(bot_id: str) -> None:
    """Delete all telegram links. Used for cleanup when a bot is removed."""
    db = _get_client()
    docs = db.collection(TELEGRAM_LINKS_COLLECTION).stream()
    for doc in docs:
        doc.reference.delete()


# ---------------------------------------------------------------------------
# Link code storage
# ---------------------------------------------------------------------------


def save_link_code(code: str, room_id: str, app_uid: str, expires_at: datetime) -> None:
    """Save a one-time link code with an expiry time."""
    db = _get_client()
    db.collection(LINK_CODES_COLLECTION).document(code).set({
        "code": code,
        "room_id": room_id,
        "app_uid": app_uid,
        "expires_at": expires_at,
    })


def get_and_consume_link_code(code: str) -> dict | None:
    """Get a link code, check expiry, delete it (one-time use).

    Returns {room_id, app_uid} or None if expired/missing.
    """
    db = _get_client()
    ref = db.collection(LINK_CODES_COLLECTION).document(code)
    doc = ref.get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    # Delete immediately (one-time use)
    ref.delete()
    # Check expiry
    expires_at = data.get("expires_at")
    if expires_at is not None:
        # Handle both datetime objects and ISO strings
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if _utcnow() > expires_at:
            return None
    return {"room_id": data["room_id"], "app_uid": data["app_uid"]}


# ---------------------------------------------------------------------------
# Chat session storage
# ---------------------------------------------------------------------------


def get_or_create_session(room_id: str, telegram_chat_id: str, app_uid: str) -> ChatSession:
    """Look up a chat session by (room_id, telegram_chat_id), create if missing."""
    db = _get_client()
    docs = (
        db.collection(CHAT_SESSIONS_COLLECTION)
        .where("room_id", "==", room_id)
        .where("telegram_chat_id", "==", telegram_chat_id)
        .limit(1)
        .stream()
    )
    for doc in docs:
        return ChatSession.from_dict(doc.to_dict())
    # Create new session
    session = ChatSession(
        session_id=str(uuid.uuid4()),
        room_id=room_id,
        telegram_chat_id=telegram_chat_id,
        app_uid=app_uid,
    )
    db.collection(CHAT_SESSIONS_COLLECTION).document(session.session_id).set(
        session.to_dict()
    )
    return session


def append_turn(session_id: str, turn: ChatTurn) -> None:
    """Append a turn to a chat session's turns array."""
    from google.cloud.firestore_v1 import ArrayUnion

    db = _get_client()
    db.collection(CHAT_SESSIONS_COLLECTION).document(session_id).update({
        "turns": ArrayUnion([turn.to_dict()]),
        "updated_at": _utcnow(),
    })


def clear_session(session_id: str) -> None:
    """Clear all turns from a chat session."""
    db = _get_client()
    db.collection(CHAT_SESSIONS_COLLECTION).document(session_id).update({
        "turns": [],
        "updated_at": _utcnow(),
    })


def get_recent_turns(session_id: str, limit: int = 20) -> list[ChatTurn]:
    """Return the last N turns from a chat session."""
    db = _get_client()
    doc = db.collection(CHAT_SESSIONS_COLLECTION).document(session_id).get()
    if not doc.exists:
        return []
    data = doc.to_dict()
    raw_turns = data.get("turns", [])
    recent = raw_turns[-limit:] if len(raw_turns) > limit else raw_turns
    return [ChatTurn.from_dict(t) for t in recent]
