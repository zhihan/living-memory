"""Telegram chat handler — processes messages from linked users through the assistant.

Loads chat session history, builds room context, calls the assistant,
sends the response via Telegram, and persists the conversation turns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

import room_storage
import series_storage
import telegram_storage
from assistant import run_assistant_stream
from assistant_actions import execute_action, get_pending_action, update_pending_action_status
from models import ChatTurn, TelegramBotConfig

logger = logging.getLogger(__name__)

_MAX_INPUT_LENGTH = 2000


async def _send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    """Send a text message via the Telegram Bot API."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


async def _send_telegram_message_with_inline_keyboard(
    bot_token: str, chat_id: str, text: str, reply_markup: dict,
) -> None:
    """Send a text message with an inline keyboard via the Telegram Bot API."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "reply_markup": reply_markup},
        )


async def _edit_telegram_message(
    bot_token: str, chat_id: str, message_id: int, text: str,
) -> None:
    """Edit an existing Telegram message."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
        )


async def _answer_callback_query(bot_token: str, callback_query_id: str) -> None:
    """Answer a Telegram callback query to dismiss the loading state."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
        )


def _build_room_context(room_id: str) -> dict | None:
    """Build a room context dict for the assistant, matching the app's pattern."""
    room = room_storage.get_room(room_id)
    if room is None:
        return None
    all_series = series_storage.list_series_for_room(room_id)
    occs = series_storage.list_occurrences_for_room(room_id, status="scheduled")
    return {
        "room_id": room.room_id,
        "title": room.title,
        "timezone": room.timezone,
        "description": room.description,
        "series": [
            {
                "series_id": s.series_id,
                "title": s.title,
                "kind": s.kind,
                "schedule_rule": s.schedule_rule.to_dict(),
                "default_time": s.default_time,
                "status": s.status,
            }
            for s in all_series
        ],
        "upcoming_occurrences": [
            {
                "occurrence_id": o.occurrence_id,
                "series_id": o.series_id,
                "scheduled_for": o.scheduled_for,
                "status": o.status,
                "host": o.host,
                "location": o.location,
            }
            for o in occs[:20]
        ],
    }


async def handle_telegram_message(
    bot_config: TelegramBotConfig,
    telegram_user_id: str,
    app_uid: str,
    chat_id: str,
    text: str,
) -> None:
    """Process a text message from a linked Telegram user through the assistant."""
    # Input length cap
    if len(text) > _MAX_INPUT_LENGTH:
        await _send_telegram_message(
            bot_config.bot_token,
            chat_id,
            f"Message too long (max {_MAX_INPUT_LENGTH} characters). Please shorten it.",
        )
        return

    # Load/create chat session
    session = telegram_storage.get_or_create_session(
        bot_config.room_id, chat_id, app_uid
    )

    # Get recent turns as history
    recent_turns = telegram_storage.get_recent_turns(session.session_id, limit=20)
    history = [{"role": t.role, "text": t.text} for t in recent_turns]

    # Build room context
    room_context = _build_room_context(bot_config.room_id)

    # Call the assistant
    response_text = ""
    action_proposal = None
    try:
        for event in run_assistant_stream(
            message=text,
            room_id=bot_config.room_id,
            uid=app_uid,
            room_context=room_context,
            history=history,
        ):
            event_type = event.get("type")
            if event_type == "text_chunk":
                response_text += event.get("text", "")
            elif event_type == "action_proposal":
                if bot_config.mode == "read_write":
                    action_proposal = event
                # In read_only mode, discard action proposals
            elif event_type == "error":
                logger.error(
                    "Assistant error for room %s: %s",
                    bot_config.room_id,
                    event.get("message"),
                )
                if not response_text:
                    response_text = "Sorry, something went wrong. Please try again."
    except Exception:
        logger.exception("Assistant stream failed for room %s", bot_config.room_id)
        response_text = "Sorry, something went wrong. Please try again."

    # If read_write and there's an action proposal, send with inline buttons
    action_id = None
    if action_proposal:
        preview = action_proposal.get("preview_summary", "")
        action_id = action_proposal.get("action_id")

    if not response_text:
        response_text = "I'm not sure how to help with that. Could you rephrase?"

    # Send response via Telegram
    await _send_telegram_message(bot_config.bot_token, chat_id, response_text)

    # Send action proposal as a separate message with inline buttons
    if action_proposal and action_id and preview:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "\u2705 Confirm", "callback_data": f"confirm:{action_id}"},
                {"text": "\u274c Cancel", "callback_data": f"cancel:{action_id}"},
            ]]
        }
        await _send_telegram_message_with_inline_keyboard(
            bot_config.bot_token, chat_id, f"Proposed action: {preview}", reply_markup,
        )

    # Persist turns
    now = datetime.now(timezone.utc)
    user_turn = ChatTurn(role="user", text=text, timestamp=now)
    assistant_turn = ChatTurn(
        role="assistant", text=response_text, timestamp=now, action_id=action_id
    )
    telegram_storage.append_turn(session.session_id, user_turn)
    telegram_storage.append_turn(session.session_id, assistant_turn)


async def handle_telegram_callback(
    bot_config: TelegramBotConfig,
    telegram_user_id: str,
    app_uid: str,
    callback_query: dict,
) -> None:
    """Handle a Telegram callback query (confirm/cancel inline button press)."""
    callback_query_id = str(callback_query.get("id", ""))
    callback_data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    message_id = message.get("message_id")

    if not callback_data or ":" not in callback_data:
        await _answer_callback_query(bot_config.bot_token, callback_query_id)
        return

    action_type, action_id = callback_data.split(":", 1)
    if action_type not in ("confirm", "cancel"):
        await _answer_callback_query(bot_config.bot_token, callback_query_id)
        return

    # Look up the pending action
    pending = get_pending_action(action_id)
    if pending is None:
        await _edit_telegram_message(
            bot_config.bot_token, chat_id, message_id,
            "Action not found or expired.",
        )
        await _answer_callback_query(bot_config.bot_token, callback_query_id)
        return

    # Verify action belongs to this room
    if pending.room_id != bot_config.room_id:
        await _edit_telegram_message(
            bot_config.bot_token, chat_id, message_id,
            "This action does not belong to this room.",
        )
        await _answer_callback_query(bot_config.bot_token, callback_query_id)
        return

    # Verify requesting user matches
    if pending.requested_by_uid != app_uid:
        await _edit_telegram_message(
            bot_config.bot_token, chat_id, message_id,
            "Only the user who requested this action can confirm or cancel it.",
        )
        await _answer_callback_query(bot_config.bot_token, callback_query_id)
        return

    # Check action is still pending
    if pending.status != "pending":
        await _edit_telegram_message(
            bot_config.bot_token, chat_id, message_id,
            f"Action is already {pending.status}.",
        )
        await _answer_callback_query(bot_config.bot_token, callback_query_id)
        return

    preview = pending.preview_summary
    result_text = ""

    if action_type == "confirm":
        try:
            update_pending_action_status(action_id, "confirmed")
            result = execute_action(pending)
            update_pending_action_status(action_id, "executed", result=result)
            result_text = f"\u2705 Done: {preview}"
        except Exception as exc:
            logger.exception("Action execution failed: %s", action_id)
            update_pending_action_status(action_id, "failed", error=str(exc))
            result_text = f"\u274c Failed: {preview}\nError: {exc}"
    else:
        update_pending_action_status(action_id, "cancelled")
        result_text = f"\u274c Cancelled: {preview}"

    # Edit the original message to show the result
    await _edit_telegram_message(
        bot_config.bot_token, chat_id, message_id, result_text,
    )
    await _answer_callback_query(bot_config.bot_token, callback_query_id)

    # Append result to chat session for context
    session = telegram_storage.get_or_create_session(
        bot_config.room_id, chat_id, app_uid,
    )
    result_turn = ChatTurn(
        role="assistant",
        text=result_text,
        timestamp=datetime.now(timezone.utc),
        action_id=action_id,
    )
    telegram_storage.append_turn(session.session_id, result_turn)
