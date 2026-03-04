"""Timezone-aware date helpers.

The service defaults to UTC internally.  Each *page* stores its own
timezone; callers resolve that via ``resolve_tz()`` before calling
``today()``.  Pages without a timezone fall back to ``LEGACY_TZ``
(America/New_York) for backwards compatibility with pre-per-page data.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("UTC")
LEGACY_TZ = ZoneInfo("America/New_York")


def resolve_tz(tz_name: str | None) -> ZoneInfo:
    """Return ``ZoneInfo(tz_name)`` if given, else ``LEGACY_TZ``."""
    if tz_name is None:
        return LEGACY_TZ
    return ZoneInfo(tz_name)


def today(tz: ZoneInfo | None = None) -> date:
    """Return today's date in *tz* (default: UTC)."""
    return datetime.now(tz or DEFAULT_TZ).date()
