"""Committer — accepts free-form text, uses AI to create/update memory files."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from cleanup import cleanup
from memory import Memory, _next_sunday
from storage import upload_to_gcs

load_dotenv()



def slugify(title: str | None, target: date, slug: str | None = None) -> str:
    """Generate a filename from the title and target date."""
    prefix = target.isoformat() if target else "ongoing"
    if slug:
        clean = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
        if clean:
            return f"{prefix}-{clean}.md"
    if not title:
        return f"{prefix}.md"
    clean = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not clean:
        return f"{prefix}.md"
    return f"{prefix}-{clean}.md"


def load_memories(memories_dir: Path, user_id: str | None = None) -> list[Memory]:
    """Load all memories from the directory (no date filtering).

    If *user_id* is given, only memories belonging to that user are returned.
    """
    memories = []
    for path in sorted(memories_dir.glob("*.md")):
        mem = Memory.load(path)
        if user_id is not None and mem.user_id != user_id:
            continue
        memories.append(mem)
    return memories


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
    """Call Gemini and return the parsed JSON response."""
    from google import genai  # noqa: E402

    api_key = os.environ["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return json.loads(response.text)


def git_commit_and_push(path: Path, push: bool = True) -> None:
    """Stage, commit, and optionally push the memory file."""
    subprocess.run(["git", "add", str(path)], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Update memory: {path.name}"],
        check=True,
    )
    if push:
        subprocess.run(["git", "push"], check=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Commit a memory to the repository")
    parser.add_argument("--memories-dir", type=Path, default=Path("memories"))
    parser.add_argument("--message", required=True, help="Free-form text describing the event")
    parser.add_argument("--today", type=date.fromisoformat, default=None,
                        help="Override today's date for testing")
    parser.add_argument("--attach", type=Path, action="append", default=[],
                        help="File(s) to upload as attachments (repeatable)")
    parser.add_argument("--user-id", type=str, default="cambridge-lexington",
                        help="Owner of the memory (default: 'cambridge-lexington')")
    parser.add_argument("--no-push", action="store_true", help="Skip git push")
    args = parser.parse_args(argv)

    today = args.today or date.today()
    memories_dir: Path = args.memories_dir

    # Upload attachments to GCS
    attachment_urls: list[str] = []
    for attach_path in args.attach:
        url = upload_to_gcs(attach_path)
        attachment_urls.append(url)

    existing_memories = load_memories(memories_dir, user_id=args.user_id)
    prompt = build_ai_request(args.message, existing_memories, today,
                              attachment_urls=attachment_urls or None)
    result = call_ai(prompt)

    raw_target = result.get("target")
    target = date.fromisoformat(raw_target) if raw_target else None
    expires = date.fromisoformat(result["expires"]) if result.get("expires") else _next_sunday(today)
    raw_attachments = result.get("attachments")
    mem = Memory(
        target=target,
        expires=expires,
        content=result["content"],
        title=result.get("title"),
        time=result.get("time"),
        place=result.get("place"),
        attachments=raw_attachments if raw_attachments else None,
        user_id=args.user_id,
    )

    slug = result.get("slug")

    if result["action"] == "update" and result.get("update_title"):
        # Find existing file by matching title
        path = None
        for p in memories_dir.glob("*.md"):
            existing = Memory.load(p)
            if existing.title == result["update_title"]:
                path = p
                break
        if path is None:
            path = memories_dir / slugify(mem.title, target, slug=slug)
    else:
        path = memories_dir / slugify(mem.title, target, slug=slug)

    # Remove expired memories before committing the new one.
    cleanup(memories_dir, today, push=False)

    mem.dump(path)
    git_commit_and_push(path, push=not args.no_push)


if __name__ == "__main__":
    main()
