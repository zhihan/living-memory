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

from memory import Memory

load_dotenv()


def slugify(title: str | None, target: date) -> str:
    """Generate a filename from the title and target date."""
    prefix = target.isoformat()
    if not title:
        return f"{prefix}.md"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{prefix}-{slug}.md"


def load_memories(memories_dir: Path) -> list[Memory]:
    """Load all memories from the directory (no date filtering)."""
    memories = []
    for path in sorted(memories_dir.glob("*.md")):
        memories.append(Memory.load(path))
    return memories


def build_ai_request(message: str, existing_memories: list[Memory], today: date) -> str:
    """Build a prompt for the AI from the user message, existing memories, and today's date."""
    memory_summaries = []
    for mem in existing_memories:
        parts = [f"target={mem.target.isoformat()}"]
        if mem.title:
            parts.append(f"title={mem.title}")
        if mem.time:
            parts.append(f"time={mem.time}")
        if mem.place:
            parts.append(f"place={mem.place}")
        parts.append(f"expires={mem.expires.isoformat()}")
        memory_summaries.append(", ".join(parts))

    memories_block = "\n".join(f"- {s}" for s in memory_summaries) if memory_summaries else "(none)"

    return f"""\
Today's date: {today.isoformat()}

Existing memories:
{memories_block}

User message: {message}

Respond with a single JSON object (no markdown fences) containing:
- "action": "create" or "update"
- "update_title": (only if action is "update") the title of the existing memory to overwrite
- "target": ISO 8601 date string for when the event occurs
- "expires": ISO 8601 date string for when the memory can be removed (default: 30 days after target)
- "title": short event name in markdown format; use [title](url) to make it a clickable link if a URL is relevant
- "time": time of day as a string (e.g. "10:00") or null
- "place": location string or null
- "content": event description in markdown format (use [text](url) for any links)

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
    parser.add_argument("--no-push", action="store_true", help="Skip git push")
    args = parser.parse_args(argv)

    today = args.today or date.today()
    memories_dir: Path = args.memories_dir

    existing_memories = load_memories(memories_dir)
    prompt = build_ai_request(args.message, existing_memories, today)
    result = call_ai(prompt)

    target = date.fromisoformat(result["target"])
    expires = date.fromisoformat(result["expires"])
    mem = Memory(
        target=target,
        expires=expires,
        content=result["content"],
        title=result.get("title"),
        time=result.get("time"),
        place=result.get("place"),
    )

    if result["action"] == "update" and result.get("update_title"):
        # Find existing file by matching title
        path = None
        for p in memories_dir.glob("*.md"):
            existing = Memory.load(p)
            if existing.title == result["update_title"]:
                path = p
                break
        if path is None:
            path = memories_dir / slugify(mem.title, target)
    else:
        path = memories_dir / slugify(mem.title, target)

    mem.dump(path)
    git_commit_and_push(path, push=not args.no_push)


if __name__ == "__main__":
    main()
