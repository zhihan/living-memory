"""Core data structures for memory entries."""

from __future__ import annotations

import frontmatter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


def _next_sunday(d: date) -> date:
    """Return the coming Sunday (same day if *d* is already Sunday)."""
    days_ahead = 6 - d.weekday()  # Monday=0, Sunday=6
    return d + timedelta(days=days_ahead)


@dataclass
class Memory:
    """A single memory entry.

    Each memory has a target date (when the event occurs) and an
    expiration date (when it can safely be removed from memory).
    When *target* is ``None`` the memory is **ongoing** — it has no
    specific event date and expires on the coming Sunday.
    """

    target: date | None
    expires: date
    content: str
    title: str | None = None
    time: str | None = None
    place: str | None = None
    attachments: list[str] | None = None
    user_id: str = "cambridge-lexington"

    @classmethod
    def load(cls, path: Path) -> Memory:
        """Load a memory from a markdown file with YAML frontmatter."""
        post = frontmatter.load(path)
        raw_target = post.metadata.get("target")
        raw_attachments = post.metadata.get("attachments")
        return cls(
            target=_parse_date(raw_target) if raw_target is not None else None,
            expires=_parse_date(post.metadata["expires"]),
            content=post.content,
            title=post.metadata.get("title"),
            time=post.metadata.get("time"),
            place=post.metadata.get("place"),
            attachments=list(raw_attachments) if raw_attachments else None,
            user_id=post.metadata.get("user_id", "cambridge-lexington"),
        )

    def dump(self, path: Path) -> None:
        """Write this memory to a markdown file with YAML frontmatter."""
        metadata: dict = {}
        if self.target is not None:
            metadata["target"] = self.target.isoformat()
        metadata["expires"] = self.expires.isoformat()
        if self.title is not None:
            metadata["title"] = self.title
        if self.time is not None:
            metadata["time"] = self.time
        if self.place is not None:
            metadata["place"] = self.place
        if self.attachments:
            metadata["attachments"] = self.attachments
        metadata["user_id"] = self.user_id
        post = frontmatter.Post(self.content, **metadata)
        path.write_text(frontmatter.dumps(post) + "\n")

    def is_expired(self, today: date | None = None) -> bool:
        """Check whether this memory has passed its expiration date."""
        if today is None:
            today = date.today()
        return today > self.expires


def _parse_date(value: str | date) -> date:
    """Parse a date from a string or pass through if already a date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
