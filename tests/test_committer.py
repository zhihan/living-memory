"""Tests for the committer module."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from memory import Memory
from committer import build_ai_request, main, slugify


def test_slugify():
    assert slugify("Team Meeting", date(2026, 3, 1)) == "2026-03-01-team-meeting.md"


def test_slugify_special_chars():
    assert slugify("Q&A Session!!", date(2026, 3, 1)) == "2026-03-01-q-a-session.md"


def test_slugify_no_title():
    assert slugify(None, date(2026, 3, 1)) == "2026-03-01.md"


def test_slugify_ongoing():
    assert slugify("Sunday Worship", None) == "ongoing-sunday-worship.md"


def test_slugify_ongoing_no_title():
    assert slugify(None, None) == "ongoing.md"

def test_slugify_with_slug():
    assert slugify("工作午餐", date(2026, 3, 1), slug="work-lunch") == "2026-03-01-work-lunch.md"


def test_slugify_chinese_title_no_slug():
    assert slugify("工作午餐", date(2026, 3, 1)) == "2026-03-01.md"


def test_slugify_slug_preferred_over_title():
    assert slugify("Team Meeting", date(2026, 3, 1), slug="team-sync") == "2026-03-01-team-sync.md"


def test_build_ai_request():
    memories = [
        Memory(target=date(2026, 3, 1), expires=date(2026, 4, 1),
               content="Planning", title="Standup", time="10:00", place="Room A"),
    ]
    prompt = build_ai_request("Team meeting next Thursday", memories, date(2026, 2, 18))

    assert "2026-02-18" in prompt
    assert "Team meeting next Thursday" in prompt
    assert "Standup" in prompt
    assert "10:00" in prompt
    assert "Room A" in prompt
    assert "slug" in prompt.lower()


def test_build_ai_request_ongoing_memory():
    memories = [
        Memory(target=None, expires=date(2026, 2, 22),
               content="Every week", title="Sunday Worship"),
    ]
    prompt = build_ai_request("What's happening?", memories, date(2026, 2, 18))
    assert "target=ongoing" in prompt
    assert "Sunday Worship" in prompt


def test_build_ai_request_no_memories():
    prompt = build_ai_request("New event Friday", [], date(2026, 2, 18))

    assert "(none)" in prompt
    assert "New event Friday" in prompt


def test_call_ai():
    mock_response = MagicMock()
    mock_response.text = '{"action": "create", "target": "2026-03-01", "expires": "2026-03-31", "title": "Meeting", "time": null, "place": null, "content": "Team sync"}'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
        from committer import call_ai
        result = call_ai("test prompt")

    assert result["action"] == "create"
    assert result["title"] == "Meeting"
    mock_genai.Client.assert_called_once_with(api_key="test-key")


@patch("committer.git_commit_and_push")
@patch("committer.call_ai")
def test_main_create(mock_call_ai, mock_git, tmp_path: Path):
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()

    mock_call_ai.return_value = {
        "action": "create",
        "target": "2026-03-05",
        "expires": "2026-04-04",
        "title": "Team Meeting",
        "time": "10:00",
        "place": "Room A",
        "content": "Weekly planning session",
    }

    main([
        "--memories-dir", str(mem_dir),
        "--message", "Team meeting next Thursday at 10am in Room A",
        "--today", "2026-02-18",
        "--no-push",
    ])

    files = list(mem_dir.glob("*.md"))
    assert len(files) == 1
    mem = Memory.load(files[0])
    assert mem.title == "Team Meeting"
    assert mem.time == "10:00"
    assert mem.place == "Room A"
    assert mem.content == "Weekly planning session"
    assert files[0].name == "2026-03-05-team-meeting.md"
    mock_git.assert_called_once()


@patch("committer.git_commit_and_push")
@patch("committer.call_ai")
def test_main_update(mock_call_ai, mock_git, tmp_path: Path):
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()

    # Create an existing memory
    existing = Memory(target=date(2026, 3, 5), expires=date(2026, 4, 4),
                      content="Old content", title="Team Meeting", time="10:00")
    existing.dump(mem_dir / "2026-03-05-team-meeting.md")

    mock_call_ai.return_value = {
        "action": "update",
        "update_title": "Team Meeting",
        "target": "2026-03-05",
        "expires": "2026-04-04",
        "title": "Team Meeting",
        "time": "11:00",
        "place": "Room B",
        "content": "Updated: moved to 11am in Room B",
    }

    main([
        "--memories-dir", str(mem_dir),
        "--message", "Move team meeting to 11am in Room B",
        "--today", "2026-02-18",
        "--no-push",
    ])

    files = list(mem_dir.glob("*.md"))
    assert len(files) == 1
    mem = Memory.load(files[0])
    assert mem.time == "11:00"
    assert mem.place == "Room B"
    assert mem.content == "Updated: moved to 11am in Room B"
    assert files[0].name == "2026-03-05-team-meeting.md"
    mock_git.assert_called_once()


@patch("committer.git_commit_and_push")
@patch("committer.call_ai")
def test_main_create_ongoing(mock_call_ai, mock_git, tmp_path: Path):
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()

    mock_call_ai.return_value = {
        "action": "create",
        "target": None,
        "expires": "2026-02-22",
        "title": "Sunday Worship",
        "time": "10:00",
        "place": "Chapel",
        "content": "Sunday worship every week",
    }

    main([
        "--memories-dir", str(mem_dir),
        "--message", "Sunday worship every week at 10am in Chapel",
        "--today", "2026-02-18",
        "--no-push",
    ])

    files = list(mem_dir.glob("*.md"))
    assert len(files) == 1
    mem = Memory.load(files[0])
    assert mem.target is None
    assert mem.expires == date(2026, 2, 22)
    assert mem.title == "Sunday Worship"
    assert files[0].name == "ongoing-sunday-worship.md"
    mock_git.assert_called_once()


@patch("committer.git_commit_and_push")
@patch("committer.call_ai")
def test_main_create_with_user_id(mock_call_ai, mock_git, tmp_path: Path):
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()

    mock_call_ai.return_value = {
        "action": "create",
        "target": "2026-03-05",
        "expires": "2026-04-04",
        "title": "Alice Meeting",
        "time": "10:00",
        "place": "Room A",
        "content": "Alice's planning session",
    }

    main([
        "--memories-dir", str(mem_dir),
        "--message", "Meeting next Thursday at 10am",
        "--user-id", "alice",
        "--today", "2026-02-18",
        "--no-push",
    ])

    files = list(mem_dir.glob("*.md"))
    assert len(files) == 1
    mem = Memory.load(files[0])
    assert mem.user_id == "alice"
    assert mem.title == "Alice Meeting"


@patch("committer.git_commit_and_push")
@patch("committer.call_ai")
def test_main_filters_memories_by_user_id(mock_call_ai, mock_git, tmp_path: Path):
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()

    # Create memories for different users
    Memory(target=date(2026, 3, 5), expires=date(2026, 4, 4),
           content="Alice event", title="Alice Meeting", user_id="alice").dump(
        mem_dir / "alice.md")
    Memory(target=date(2026, 3, 6), expires=date(2026, 4, 5),
           content="Bob event", title="Bob Meeting", user_id="bob").dump(
        mem_dir / "bob.md")

    mock_call_ai.return_value = {
        "action": "create",
        "target": "2026-03-10",
        "expires": "2026-04-10",
        "title": "New Alice Event",
        "time": None,
        "place": None,
        "content": "Another alice event",
    }

    main([
        "--memories-dir", str(mem_dir),
        "--message", "New event",
        "--user-id", "alice",
        "--today", "2026-02-18",
        "--no-push",
    ])

    # The AI prompt should only include alice's memory, not bob's
    prompt = mock_call_ai.call_args[0][0]
    assert "Alice Meeting" in prompt
    assert "Bob Meeting" not in prompt


def test_build_ai_request_with_attachments():
    prompt = build_ai_request(
        "Meeting with flyer", [], date(2026, 2, 18),
        attachment_urls=["https://storage.googleapis.com/bucket/flyer.pdf"],
    )
    assert "https://storage.googleapis.com/bucket/flyer.pdf" in prompt
    assert "Attached file URLs" in prompt


def test_build_ai_request_no_attachments():
    prompt = build_ai_request("Meeting", [], date(2026, 2, 18))
    assert "Attached file URLs" not in prompt


@patch("committer.git_commit_and_push")
@patch("committer.call_ai")
@patch("committer.upload_to_gcs")
def test_main_with_attachments(mock_upload, mock_call_ai, mock_git, tmp_path: Path):
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()

    # Create a fake attachment file
    attachment = tmp_path / "flyer.pdf"
    attachment.write_bytes(b"fake-pdf")

    mock_upload.return_value = "https://storage.googleapis.com/bucket/flyer.pdf"
    mock_call_ai.return_value = {
        "action": "create",
        "target": "2026-03-05",
        "expires": "2026-04-04",
        "title": "Conference",
        "time": None,
        "place": None,
        "content": "See attached flyer",
        "attachments": ["https://storage.googleapis.com/bucket/flyer.pdf"],
    }

    main([
        "--memories-dir", str(mem_dir),
        "--message", "Conference with flyer",
        "--attach", str(attachment),
        "--today", "2026-02-18",
        "--no-push",
    ])

    mock_upload.assert_called_once_with(attachment)
    files = list(mem_dir.glob("*.md"))
    assert len(files) == 1
    mem = Memory.load(files[0])
    assert mem.attachments == ["https://storage.googleapis.com/bucket/flyer.pdf"]
    mock_git.assert_called_once()
