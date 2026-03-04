"""Timezone-aware date helpers.

All date logic defaults to America/New_York so that ``today()`` matches
the intuitive "today" for the primary user base, regardless of whether
the code runs on a developer laptop or a Cloud Run container in UTC.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("America/New_York")


def today(tz: ZoneInfo | None = None) -> date:
    """Return today's date in *tz* (default: America/New_York)."""
    return datetime.now(tz or DEFAULT_TZ).date()
