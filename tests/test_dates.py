"""Tests for timezone-aware date helpers."""

from datetime import date, datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from dates import today, DEFAULT_TZ


def test_today_returns_date():
    """today() returns a date object."""
    result = today()
    assert isinstance(result, date)


def test_today_uses_eastern_by_default():
    """today() uses America/New_York, not UTC."""
    # Simulate 2026-03-03 at 23:30 UTC = 2026-03-03 18:30 ET (EST, UTC-5)
    fake_utc = datetime(2026, 3, 3, 23, 30, tzinfo=timezone.utc)
    with patch("dates.datetime") as mock_dt:
        mock_dt.now.return_value = fake_utc.astimezone(DEFAULT_TZ)
        result = today()
    assert result == date(2026, 3, 3)


def test_today_utc_midnight_is_still_yesterday_eastern():
    """At 00:30 UTC on March 4, it's still March 3 in Eastern time."""
    fake_utc = datetime(2026, 3, 4, 0, 30, tzinfo=timezone.utc)
    eastern = ZoneInfo("America/New_York")
    # Convert to Eastern: 2026-03-03 19:30 EST
    eastern_time = fake_utc.astimezone(eastern)
    with patch("dates.datetime") as mock_dt:
        mock_dt.now.return_value = eastern_time
        result = today()
    assert result == date(2026, 3, 3), (
        "At 00:30 UTC (19:30 ET), today() should return March 3, not March 4"
    )


def test_today_accepts_explicit_timezone():
    """today(tz=...) uses the given timezone."""
    utc = ZoneInfo("UTC")
    # At 2026-03-04 00:30 UTC, UTC date is March 4
    fake_utc = datetime(2026, 3, 4, 0, 30, tzinfo=timezone.utc)
    with patch("dates.datetime") as mock_dt:
        mock_dt.now.return_value = fake_utc
        result = today(tz=utc)
    assert result == date(2026, 3, 4)
