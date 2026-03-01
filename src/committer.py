"""Committer — accepts free-form text, uses AI to create/update memory files."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from memory import Memory, _next_sunday
from storage import upload_to_gcs

load_dotenv()

logger = logging.getLogger(__name__)

_MAX_AI_RETRIES = 2

# Regex to find URLs in plain text (not inside markdown link syntax)
_URL_RE = re.compile(r'https?://[^\s)\]>]+')
# Regex to detect a markdown link: [text](url)
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def extract_urls(text: str) -> list[str]:
    """Extract all http/https URLs from plain text, preserving order."""
    return _URL_RE.findall(text)


def replace_urls_with_placeholders(text: str) -> tuple[str, list[str]]:
    """Replace URLs in *text* with numbered placeholders.

    Returns ``(sanitised_text, urls)`` where each URL in the original is
    replaced by ``[link1]``, ``[link2]``, etc.  The caller can later use
    ``apply_user_urls`` to inject the real URLs back into the AI output.
    """
    urls: list[str] = []

    def _sub(m: re.Match) -> str:
        urls.append(m.group(0))
        return f"[link{len(urls)}]"

    sanitised = _URL_RE.sub(_sub, text)
    return sanitised, urls


def apply_user_urls(title: str | None, content: str, user_urls: list[str]) -> tuple[str, str]:
    """Post-process AI result to prefer user-provided URLs.

    - Title: ensure it links to the first user URL.
    - Content: ensure all user URLs appear (append Links section if needed).
    """
    if not user_urls:
        return title or "", content

    first_url = user_urls[0]

    # --- title ---
    if title:
        md_match = _MD_LINK_RE.search(title)
        if md_match:
            # Title already has a markdown link — replace its URL with the first user URL
            title = title[:md_match.start(2)] + first_url + title[md_match.end(2):]
        else:
            # Wrap the whole title text as a link
            title = f"[{title}]({first_url})"

    # --- content: ensure every user URL is present ---
    missing = [u for u in user_urls if u not in content]
    if missing:
        links_section = "\n\nLinks:\n" + "\n".join(f"- {u}" for u in missing)
        content = content + links_section

    return title, content


def build_ai_request(message: str, existing_memories: list[Memory], today: date, attachment_urls: list[str] | None = None) -> str:
    """Build a prompt for the AI from the user message, existing memories, and today's date."""
    memory_summaries = []
    for mem in existing_memories:
        parts = []
        if mem.target is not None:
            parts.append(f"target={mem.target.isoformat()}")
        else:
            parts.append("target=ongoing")
        if mem.title:
            parts.append(f"title={mem.title}")
        if mem.time:
            parts.append(f"time={mem.time}")
        if mem.place:
            parts.append(f"place={mem.place}")
        parts.append(f"expires={mem.expires.isoformat()}")
        memory_summaries.append(", ".join(parts))

    memories_block = "\n".join(f"- {s}" for s in memory_summaries) if memory_summaries else "(none)"

    attachments_block = ""
    if attachment_urls:
        urls = "\n".join(f"- {url}" for url in attachment_urls)
        attachments_block = f"""
Attached file URLs (already uploaded):
{urls}
"""

    return f"""\
Today's date: {today.isoformat()}

Existing memories:
{memories_block}

User message: {message}
{attachments_block}
Respond in the same language as the user's message.
When matching events, treat semantically equivalent events across languages as the same event (e.g. "work lunch" and "工作午餐" refer to the same event).

Respond with a single JSON object (no markdown fences) containing:
- "action": "create" or "update"
- "update_title": (only if action is "update") the title of the existing memory to overwrite
- "target": ISO 8601 date string for when the event occurs, or null for ongoing/recurring events with no specific date
- "expires": ISO 8601 date string for when the memory can be removed (default: 30 days after target; use the coming Sunday for ongoing events)
- "title": short event name in markdown format; use [title](url) to make it a clickable link if a URL is relevant
- "slug": ASCII-only short identifier for the filename (e.g. "work-lunch" for "工作午餐")
- "time": time of day as a string (e.g. "10:00") or null
- "place": location string or null
- "content": event description in markdown format (use [text](url) for any links)
- "attachments": list of attachment URLs to store with this memory (include any uploaded file URLs that are relevant), or null if none

Use "update" when the user's message refers to an event that clearly matches an existing memory. Otherwise use "create"."""


def call_ai(prompt: str) -> dict:
    """Call Gemini and return the parsed JSON response.

    Retries up to ``_MAX_AI_RETRIES`` times when the model returns an empty
    or unparseable response (common with complex unicode/URL inputs).
    """
    from google import genai  # noqa: E402
    from google.genai import types  # noqa: E402

    api_key = os.environ["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)

    last_exc: Exception | None = None
    for attempt in range(_MAX_AI_RETRIES):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        text = response.text
        if not text or not text.strip():
            last_exc = ValueError("Gemini returned an empty response")
            logger.warning("call_ai attempt %d: empty response, retrying", attempt + 1)
            continue
        try:
            result = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            last_exc = exc
            logger.warning("call_ai attempt %d: invalid JSON (%s), retrying", attempt + 1, exc)
            continue

        # Validate required keys
        if "action" not in result or "content" not in result:
            last_exc = ValueError(f"AI response missing required keys: {sorted(result.keys())}")
            logger.warning("call_ai attempt %d: %s, retrying", attempt + 1, last_exc)
            continue

        return result

    raise last_exc or ValueError("AI call failed after retries")


@dataclass
class CommitResult:
    """Result of committing a memory via the core function."""
    action: str
    doc_id: str | None
    memory: Memory


def commit_memory_firestore(
    message: str,
    user_id: str,
    today: date | None = None,
    attachment_urls: list[str] | None = None,
    page_id: str | None = None,
) -> CommitResult:
    """Core function: process a message and save to Firestore.

    Returns a ``CommitResult`` with the action taken, document ID, and Memory.
    """
    import firestore_storage

    if today is None:
        today = date.today()

    if page_id:
        pairs = firestore_storage.load_memories_by_page(page_id, today)
    else:
        pairs = firestore_storage.load_memories(user_id, today)
    existing_memories = [mem for _, mem in pairs]

    # Replace complex URLs with placeholders so Gemini sees clean input.
    sanitised_message, user_urls = replace_urls_with_placeholders(message)

    prompt = build_ai_request(sanitised_message, existing_memories, today,
                              attachment_urls=attachment_urls or None)
    result = call_ai(prompt)

    _NONE_STRINGS = {"ongoing", "recurring", "none", "null", ""}

    raw_target = result.get("target")
    if isinstance(raw_target, str) and raw_target.strip().lower() in _NONE_STRINGS:
        raw_target = None
    target = date.fromisoformat(raw_target) if raw_target else None

    raw_expires = result.get("expires")
    if isinstance(raw_expires, str) and raw_expires.strip().lower() in _NONE_STRINGS:
        raw_expires = None
    expires = date.fromisoformat(raw_expires) if raw_expires else _next_sunday(today)
    raw_attachments = result.get("attachments")

    # Restore real URLs into AI output
    ai_title = result.get("title") or ""
    ai_content = result["content"]
    if user_urls:
        ai_title, ai_content = apply_user_urls(ai_title, ai_content, user_urls)

    mem = Memory(
        target=target,
        expires=expires,
        content=ai_content,
        title=ai_title or result.get("title"),
        time=result.get("time"),
        place=result.get("place"),
        attachments=raw_attachments if raw_attachments else None,
        user_id=user_id,
        page_id=page_id,
    )

    doc_id = None
    if result["action"] == "update" and result.get("update_title"):
        if page_id:
            found = firestore_storage.find_memory_by_title_on_page(
                page_id, result["update_title"], today,
            )
        else:
            found = firestore_storage.find_memory_by_title(
                user_id, result["update_title"], today,
            )
        if found:
            doc_id = found[0]
    saved_id = firestore_storage.save_memory(mem, doc_id=doc_id)
    firestore_storage.delete_expired(today)

    return CommitResult(action=result["action"], doc_id=saved_id, memory=mem)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Commit a memory to Firestore")
    parser.add_argument("--message", required=True, help="Free-form text describing the event")
    parser.add_argument("--today", type=date.fromisoformat, default=None,
                        help="Override today's date for testing")
    parser.add_argument("--attach", type=Path, action="append", default=[],
                        help="File(s) to upload as attachments (repeatable)")
    parser.add_argument("--user-id", type=str, default="cambridge-lexington",
                        help="Owner of the memory (default: 'cambridge-lexington')")
    args = parser.parse_args(argv)

    today = args.today or date.today()

    # Upload attachments to GCS
    attachment_urls: list[str] = []
    for attach_path in args.attach:
        url = upload_to_gcs(attach_path)
        attachment_urls.append(url)

    commit_memory_firestore(
        message=args.message,
        user_id=args.user_id,
        today=today,
        attachment_urls=attachment_urls or None,
    )


if __name__ == "__main__":
    main()
