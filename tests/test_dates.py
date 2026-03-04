"""Tests for timezone-aware date helpers."""

from datetime import date, datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from dates import today, DEFAULT_TZ, LEGACY_TZ, resolve_tz


def test_today_returns_date():
    """today() returns a date object."""
    result = today()
    assert isinstance(result, date)


def test_today_uses_utc_by_default():
    """today() uses UTC when no tz is passed."""
    # At 2026-03-04 00:30 UTC, UTC date is March 4
    fake_utc = datetime(2026, 3, 4, 0, 30, tzinfo=timezone.utc)
    with patch("dates.datetime") as mock_dt:
        mock_dt.now.return_value = fake_utc
        result = today()
    assert result == date(2026, 3, 4)


def test_default_tz_is_utc():
    """DEFAULT_TZ should be UTC."""
    assert DEFAULT_TZ == ZoneInfo("UTC")


def test_legacy_tz_is_eastern():
    """LEGACY_TZ should be America/New_York."""
    assert LEGACY_TZ == ZoneInfo("America/New_York")


def test_today_accepts_explicit_timezone():
    """today(tz=...) uses the given timezone."""
    eastern = ZoneInfo("America/New_York")
    # At 2026-03-04 00:30 UTC, Eastern date is March 3
    fake_utc = datetime(2026, 3, 4, 0, 30, tzinfo=timezone.utc)
    eastern_time = fake_utc.astimezone(eastern)
    with patch("dates.datetime") as mock_dt:
        mock_dt.now.return_value = eastern_time
        result = today(tz=eastern)
    assert result == date(2026, 3, 3)


# ---------------------------------------------------------------------------
# resolve_tz
# ---------------------------------------------------------------------------

def test_resolve_tz_none_returns_legacy():
    """resolve_tz(None) returns LEGACY_TZ (America/New_York)."""
    assert resolve_tz(None) == ZoneInfo("America/New_York")


def test_resolve_tz_valid_string():
    """resolve_tz with a valid tz name returns the corresponding ZoneInfo."""
    assert resolve_tz("Europe/London") == ZoneInfo("Europe/London")
    assert resolve_tz("America/Chicago") == ZoneInfo("America/Chicago")
    assert resolve_tz("UTC") == ZoneInfo("UTC")


def test_resolve_tz_invalid_raises():
    """resolve_tz with an invalid tz name raises an error."""
    with pytest.raises((KeyError, Exception)):
        resolve_tz("Not/A/Timezone")
