"""Regression tests for issue #80: timezone-unaware date.today() caused
update-matching to fail when the server ran in UTC and the user was in
Eastern time.

The root cause: ``date.today()`` on a UTC server returns tomorrow's date
for an Eastern-time user in the evening (after 7/8 PM ET).  This caused
memories expiring "today" (user's perspective) to be filtered out, so the
AI never saw them and created duplicates instead of updating.
"""

from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from memory import Memory
from committer import commit_memory_firestore


# ---------------------------------------------------------------------------
# Scenario: user at 8 PM Eastern (= midnight+1 UTC next day) tries to
# update an event that expires today (Eastern).  Before the fix,
# date.today() on the UTC server would return tomorrow, filtering the
# event as expired.
# ---------------------------------------------------------------------------

@patch("firestore_storage.delete_expired")
@patch("firestore_storage.save_memory")
@patch("firestore_storage.find_memory_by_title_on_page")
@patch("firestore_storage.load_memories_by_page")
@patch("committer.call_ai")
def test_update_not_blocked_by_utc_expiry(
    mock_call_ai, mock_load, mock_find, mock_save, mock_delete,
):
    """An event expiring 'today' (Eastern) must still be visible for update,
    even if a UTC server would consider it expired."""
    eastern_today = date(2026, 3, 3)

    existing = Memory(
        target=date(2026, 3, 3),
        expires=date(2026, 3, 3),  # expires today Eastern
        content="Bible study at 7pm",
        title="Bible Study",
        page_id="test-page",
    )
    mock_load.return_value = [("doc-abc", existing)]
    mock_find.return_value = ("doc-abc", existing)
    mock_save.return_value = "doc-abc"
    mock_delete.return_value = []

    mock_call_ai.return_value = {
        "action": "update",
        "update_title": "Bible Study",
        "target": "2026-03-03",
        "expires": "2026-03-03",
        "title": "Bible Study",
        "time": "19:30",
        "place": "Room 2",
        "content": "Bible study moved to 7:30pm",
    }

    result = commit_memory_firestore(
        message="Move bible study to 7:30pm",
        user_id="owner-uid",
        today=eastern_today,
        page_id="test-page",
    )

    assert result.action == "update"
    assert result.doc_id == "doc-abc"
    # The AI should have seen the existing memory
    prompt = mock_call_ai.call_args[0][0]
    assert "Bible Study" in prompt


@patch("firestore_storage.delete_expired")
@patch("firestore_storage.save_memory")
@patch("firestore_storage.find_memory_by_title_on_page")
@patch("firestore_storage.load_memories_by_page")
@patch("committer.call_ai")
def test_today_passed_to_ai_prompt_matches_eastern(
    mock_call_ai, mock_load, mock_find, mock_save, mock_delete,
):
    """The 'today' date in the AI prompt must match Eastern time, not UTC."""
    eastern_today = date(2026, 3, 3)  # March 3 in Eastern

    mock_load.return_value = []
    mock_save.return_value = "new-id"
    mock_delete.return_value = []

    mock_call_ai.return_value = {
        "action": "create",
        "target": "2026-03-05",
        "expires": "2026-04-04",
        "title": "Test Event",
        "time": None,
        "place": None,
        "content": "Test",
    }

    commit_memory_firestore(
        message="Test event on Thursday",
        user_id="owner-uid",
        today=eastern_today,
        page_id="test-page",
    )

    prompt = mock_call_ai.call_args[0][0]
    assert "2026-03-03" in prompt, (
        "AI prompt should contain March 3 (Eastern), not March 4 (UTC)"
    )


def test_is_expired_uses_eastern_today():
    """Memory.is_expired() without explicit today should use Eastern time."""
    mem = Memory(
        target=date(2026, 3, 3),
        expires=date(2026, 3, 3),
        content="Test",
    )
    # Simulate 2026-03-04 00:30 UTC = 2026-03-03 19:30 ET
    fake_utc = datetime(2026, 3, 4, 0, 30, tzinfo=timezone.utc)
    eastern = ZoneInfo("America/New_York")
    eastern_time = fake_utc.astimezone(eastern)

    with patch("dates.datetime") as mock_dt:
        mock_dt.now.return_value = eastern_time
        assert not mem.is_expired(), (
            "At 00:30 UTC (19:30 ET on March 3), a memory expiring March 3 "
            "should NOT be expired"
        )


@patch("firestore_storage.delete_expired")
@patch("firestore_storage.save_memory")
@patch("firestore_storage.load_memories_by_page")
@patch("committer.call_ai")
def test_commit_defaults_to_eastern_today(
    mock_call_ai, mock_load, mock_save, mock_delete,
):
    """commit_memory_firestore() with no explicit today= should use Eastern."""
    mock_load.return_value = []
    mock_save.return_value = "new-id"
    mock_delete.return_value = []

    mock_call_ai.return_value = {
        "action": "create",
        "target": "2026-03-05",
        "expires": "2026-04-04",
        "title": "Test",
        "time": None,
        "place": None,
        "content": "Test",
    }

    eastern_march3 = date(2026, 3, 3)
    with patch("committer._today", return_value=eastern_march3):
        result = commit_memory_firestore(
            message="Test",
            user_id="owner-uid",
            page_id="test-page",
        )

    prompt = mock_call_ai.call_args[0][0]
    assert "2026-03-03" in prompt
