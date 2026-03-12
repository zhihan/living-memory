"""Core data structures for memory entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from dates import today as _today


@dataclass
class Memory:
    """A single memory entry.

    Each memory has a target date (when the event occurs) and an
    expiration date (when it can safely be removed from memory).
    """

    target: date
    expires: date
    content: str
    title: str | None = None
    time: str | None = None
    place: str | None = None
    attachments: list[str] | None = None
    page_id: str | None = None
    visibility: str = "public"

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for Firestore storage."""
        d: dict = {
            "target": self.target.isoformat(),
            "expires": self.expires.isoformat(),
            "content": self.content,
            "title": self.title,
            "time": self.time,
            "place": self.place,
            "attachments": self.attachments,
            "page_id": self.page_id,
            "visibility": self.visibility,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Memory:
        """Deserialize from a Firestore document dict."""
        raw_attachments = data.get("attachments")
        return cls(
            target=_parse_date(data["target"]),
            expires=_parse_date(data["expires"]),
            content=data.get("content", ""),
            title=data.get("title"),
            time=data.get("time"),
            place=data.get("place"),
            attachments=list(raw_attachments) if raw_attachments else None,
            page_id=data.get("page_id"),
            visibility=data.get("visibility", "public"),
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
