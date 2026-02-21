"""Tests for memory data structures."""

from datetime import date
from pathlib import Path

from memory import Memory, _next_sunday


def test_roundtrip(tmp_path: Path):
    """A memory can be saved and loaded back identically."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Team standup at 10am.",
        title="Standup",
    )
    path = tmp_path / "standup.md"
    mem.dump(path)
    loaded = Memory.load(path)
    assert loaded == mem


def test_roundtrip_no_title(tmp_path: Path):
    """A memory without a title roundtrips correctly."""
    mem = Memory(
        target=date(2026, 6, 1),
        expires=date(2026, 7, 1),
        content="Summer break starts.",
    )
    path = tmp_path / "summer.md"
    mem.dump(path)
    loaded = Memory.load(path)
    assert loaded == mem


def test_is_expired():
    mem = Memory(
        target=date(2026, 1, 1),
        expires=date(2026, 1, 31),
        content="January event.",
    )
    assert not mem.is_expired(today=date(2026, 1, 15))
    assert not mem.is_expired(today=date(2026, 1, 31))
    assert mem.is_expired(today=date(2026, 2, 1))


def test_file_format(tmp_path: Path):
    """The on-disk format is readable markdown with YAML frontmatter."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Meeting notes here.",
        title="Planning",
    )
    path = tmp_path / "planning.md"
    mem.dump(path)
    raw = path.read_text()
    assert raw.startswith("---\n")
    assert "target: '2026-03-15'" in raw or "target: 2026-03-15" in raw
    assert "Meeting notes here." in raw


def test_roundtrip_ongoing(tmp_path: Path):
    """An ongoing memory (no target) roundtrips correctly."""
    mem = Memory(
        target=None,
        expires=date(2026, 2, 22),
        content="Sunday worship every week.",
        title="Sunday Worship",
    )
    path = tmp_path / "ongoing-worship.md"
    mem.dump(path)
    loaded = Memory.load(path)
    assert loaded == mem
    assert loaded.target is None


def test_ongoing_file_format(tmp_path: Path):
    """Ongoing memory file should not contain a target field."""
    mem = Memory(
        target=None,
        expires=date(2026, 2, 22),
        content="Recurring event.",
    )
    path = tmp_path / "ongoing.md"
    mem.dump(path)
    raw = path.read_text()
    assert "target" not in raw
    assert "expires" in raw


def test_is_expired_ongoing():
    """Ongoing memories still expire based on their expires date."""
    mem = Memory(
        target=None,
        expires=date(2026, 2, 22),
        content="Weekly event.",
    )
    assert not mem.is_expired(today=date(2026, 2, 18))
    assert not mem.is_expired(today=date(2026, 2, 22))
    assert mem.is_expired(today=date(2026, 2, 23))


def test_roundtrip_with_attachments(tmp_path: Path):
    """A memory with attachments roundtrips correctly."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="See attached flyer.",
        title="Conference",
        attachments=["https://storage.googleapis.com/bucket/a.pdf",
                     "https://storage.googleapis.com/bucket/b.png"],
    )
    path = tmp_path / "conference.md"
    mem.dump(path)
    loaded = Memory.load(path)
    assert loaded == mem
    assert loaded.attachments == [
        "https://storage.googleapis.com/bucket/a.pdf",
        "https://storage.googleapis.com/bucket/b.png",
    ]


def test_roundtrip_no_attachments(tmp_path: Path):
    """A memory without attachments has attachments=None after roundtrip."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="No files.",
    )
    path = tmp_path / "nofiles.md"
    mem.dump(path)
    loaded = Memory.load(path)
    assert loaded.attachments is None


def test_attachments_file_format(tmp_path: Path):
    """Attachments appear in the YAML frontmatter."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Flyer attached.",
        attachments=["https://example.com/flyer.pdf"],
    )
    path = tmp_path / "att.md"
    mem.dump(path)
    raw = path.read_text()
    assert "attachments" in raw
    assert "https://example.com/flyer.pdf" in raw


def test_no_attachments_not_in_file(tmp_path: Path):
    """When there are no attachments the key should not appear in the file."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Nothing attached.",
    )
    path = tmp_path / "none.md"
    mem.dump(path)
    raw = path.read_text()
    assert "attachments" not in raw


def test_roundtrip_user_id(tmp_path: Path):
    """user_id is preserved through dump/load."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Alice's event.",
        title="Alice Event",
        user_id="alice",
    )
    path = tmp_path / "alice.md"
    mem.dump(path)
    loaded = Memory.load(path)
    assert loaded.user_id == "alice"
    assert loaded == mem


def test_user_id_default(tmp_path: Path):
    """Memories without explicit user_id default to 'cambridge-lexington'."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Some event.",
    )
    assert mem.user_id == "cambridge-lexington"
    path = tmp_path / "default.md"
    mem.dump(path)
    loaded = Memory.load(path)
    assert loaded.user_id == "cambridge-lexington"


def test_user_id_in_file_format(tmp_path: Path):
    """user_id appears in the YAML frontmatter."""
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Event.",
        user_id="bob",
    )
    path = tmp_path / "bob.md"
    mem.dump(path)
    raw = path.read_text()
    assert "user_id: bob" in raw


def test_next_sunday():
    # Wednesday 2026-02-18 → Sunday 2026-02-22
    assert _next_sunday(date(2026, 2, 18)) == date(2026, 2, 22)
    # Sunday stays on Sunday
    assert _next_sunday(date(2026, 2, 22)) == date(2026, 2, 22)
    # Monday → next Sunday
    assert _next_sunday(date(2026, 2, 16)) == date(2026, 2, 22)
