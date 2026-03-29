"""Assistant service — Meeting Organizer AI assistant.

Parses organizer messages, determines intent, proposes structured actions
(with preview text), and streams a response to the caller.

Streaming events (dicts with "type" key):
  {"type": "status",          "message": "..."}
  {"type": "text_chunk",      "text": "..."}
  {"type": "action_proposal", "action_id": "...", "action_type": "...",
   "preview_summary": "...",  "payload": {...}}
  {"type": "done"}
  {"type": "error",           "message": "..."}
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Generator

from assistant_actions import (
    build_create_series_action,
    build_draft_material_action,
    build_generate_reminder_text_action,
    build_reschedule_occurrence_action,
    save_pending_action,
)

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash-lite"
_MAX_RETRIES = 2

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an AI assistant for a meeting organizer. Help organizers manage recurring
meetings, schedules, and materials through natural conversation.

Available actions:
  create_series          — create a new recurring meeting series
  reschedule_occurrence  — reschedule a single meeting occurrence
  draft_material         — draft meeting material (agenda, notes, announcement)
  generate_reminder_text — generate a shareable reminder for participants
  general_question       — answer without performing any state change

For each message:
  1. Determine the INTENT (one of the five above).
  2. Write a short, friendly RESPONSE (1-3 sentences).
  3. If the intent is state-changing, produce a structured ACTION PAYLOAD.
  4. If no action is needed, set "action" to null.

Always reply in the same language as the user.

Respond with a single JSON object (no markdown fences):
{
  "intent": "<intent>",
  "response_text": "<conversational reply>",
  "action": {
    "action_type": "<same as intent, not applicable for general_question>",
    "preview_summary": "<1-sentence summary of what will happen>",
    "payload": {
      // create_series: title, kind, description, schedule_rule{frequency,weekdays,interval},
      //   default_time, default_duration_minutes, default_location, default_online_link
      // reschedule_occurrence: occurrence_id, new_scheduled_for (ISO 8601 UTC)
      // draft_material: title, material_kind, draft_text
      // generate_reminder_text: occurrence_id, series_id, reminder_text
    }
  }
}
"""


def _build_prompt(message: str, workspace_context: dict[str, Any] | None) -> str:
    ctx = ""
    if workspace_context:
        ctx = "\nWorkspace context:\n" + json.dumps(workspace_context, indent=2, default=str) + "\n"
    return _SYSTEM_PROMPT + ctx + f"\nUser message: {message}"


# ---------------------------------------------------------------------------
# Gemini call (JSON mode)
# ---------------------------------------------------------------------------

def _call_ai(prompt: str) -> dict:
    from google import genai
    from google.genai import types

    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        text = response.text
        if not text or not text.strip():
            last_exc = ValueError("Gemini returned an empty response")
            logger.warning("assistant AI attempt %d: empty response", attempt + 1)
            continue
        try:
            result = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            last_exc = exc
            logger.warning("assistant AI attempt %d: invalid JSON: %s", attempt + 1, exc)
            continue
        if not isinstance(result, dict) or "intent" not in result:
            last_exc = ValueError(f"Unexpected AI response shape: {result!r}")
            logger.warning("assistant AI attempt %d: bad shape", attempt + 1)
            continue
        return result

    raise last_exc or ValueError("AI call failed after retries")


# ---------------------------------------------------------------------------
# Action builder dispatch
# ---------------------------------------------------------------------------

_ACTION_BUILDERS = {
    "create_series": build_create_series_action,
    "reschedule_occurrence": build_reschedule_occurrence_action,
    "draft_material": build_draft_material_action,
    "generate_reminder_text": build_generate_reminder_text_action,
}


def _build_and_save_action(
    intent: str, ai_action: dict, workspace_id: str, uid: str
):
    builder = _ACTION_BUILDERS.get(intent)
    if builder is None:
        return None
    pending = builder(workspace_id, uid, ai_action.get("payload", {}))
    if ai_action.get("preview_summary"):
        pending.preview_summary = ai_action["preview_summary"]
    save_pending_action(pending)
    return pending


# ---------------------------------------------------------------------------
# Public streaming entry point
# ---------------------------------------------------------------------------

def run_assistant_stream(
    message: str,
    workspace_id: str,
    uid: str,
    workspace_context: dict[str, Any] | None = None,
) -> Generator[dict, None, None]:
    """Stream assistant events for an organizer message."""
    yield {"type": "status", "message": "Thinking\u2026"}

    prompt = _build_prompt(message, workspace_context)
    try:
        ai_result = _call_ai(prompt)
    except Exception as exc:
        logger.exception("AI call failed in assistant stream")
        yield {"type": "error", "message": str(exc)}
        return

    intent = ai_result.get("intent", "general_question")
    response_text = ai_result.get("response_text", "")
    ai_action = ai_result.get("action")

    if response_text:
        yield {"type": "text_chunk", "text": response_text}

    if ai_action and intent != "general_question":
        try:
            pending = _build_and_save_action(intent, ai_action, workspace_id, uid)
            if pending is not None:
                yield {
                    "type": "action_proposal",
                    "action_id": pending.action_id,
                    "action_type": pending.action_type,
                    "preview_summary": pending.preview_summary,
                    "payload": pending.payload,
                }
        except Exception as exc:
            logger.exception("Failed to build/save action proposal")
            yield {"type": "status", "message": f"Could not prepare action: {exc}"}

    yield {"type": "done"}
