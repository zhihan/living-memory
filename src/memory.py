"""Core data structures for memory entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from dates import today as _today


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
    page_id: str | None = None

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for Firestore storage."""
        d: dict = {
            "target": self.target.isoformat() if self.target is not None else None,
            "expires": self.expires.isoformat(),
            "content": self.content,
            "title": self.title,
            "time": self.time,
            "place": self.place,
            "attachments": self.attachments,
            "user_id": self.user_id,
            "page_id": self.page_id,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Memory:
        """Deserialize from a Firestore document dict."""
        raw_target = data.get("target")
        raw_attachments = data.get("attachments")
        return cls(
            target=_parse_date(raw_target) if raw_target is not None else None,
            expires=_parse_date(data["expires"]),
            content=data.get("content", ""),
            title=data.get("title"),
            time=data.get("time"),
            place=data.get("place"),
            attachments=list(raw_attachments) if raw_attachments else None,
            user_id=data.get("user_id", "cambridge-lexington"),
            page_id=data.get("page_id"),
        )

    def is_expired(self, today: date | None = None) -> bool:
        """Check whether this memory has passed its expiration date."""
        if today is None:
            today = _today()
        return today > self.expires


def _parse_date(value: str | date) -> date:
    """Parse a date from a string or pass through if already a date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
