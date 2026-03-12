"""Tests for memory data structures."""

from datetime import date

from memory import Memory


def test_is_expired():
    mem = Memory(
        target=date(2026, 1, 1),
        expires=date(2026, 1, 31),
        content="January event.",
    )
    assert not mem.is_expired(today=date(2026, 1, 15))
    assert not mem.is_expired(today=date(2026, 1, 31))
    assert mem.is_expired(today=date(2026, 2, 1))


def test_to_dict():
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Team standup at 10am.",
        title="Standup",
        time="10:00",
        place="Room A",
    )
    d = mem.to_dict()
    assert d["target"] == "2026-03-15"
    assert d["expires"] == "2026-04-15"
    assert d["content"] == "Team standup at 10am."
    assert d["title"] == "Standup"
    assert d["time"] == "10:00"
    assert d["place"] == "Room A"
    assert d["attachments"] is None


def test_from_dict():
    d = {
        "target": "2026-03-15",
        "expires": "2026-04-15",
        "content": "Team standup.",
        "title": "Standup",
        "time": "10:00",
        "place": "Room A",
        "attachments": ["https://example.com/a.pdf"],
    }
    mem = Memory.from_dict(d)
    assert mem.target == date(2026, 3, 15)
    assert mem.expires == date(2026, 4, 15)
    assert mem.title == "Standup"
    assert mem.attachments == ["https://example.com/a.pdf"]


def test_to_dict_from_dict_roundtrip():
    mem = Memory(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Event.",
        title="Roundtrip",
        time="14:00",
        place="Park",
        attachments=["https://example.com/x.png"],
    )
    restored = Memory.from_dict(mem.to_dict())
    assert restored == mem


def test_from_dict_defaults():
    d = {"target": "2026-04-15", "expires": "2026-04-15", "content": "Minimal."}
    mem = Memory.from_dict(d)
    assert mem.target == date(2026, 4, 15)
    assert mem.title is None
    assert mem.attachments is None
    assert mem.visibility == "public"


def test_visibility_members():
    mem = Memory(
        target=date(2026, 3, 15), expires=date(2026, 4, 15),
        content="Private event.", visibility="members",
    )
    d = mem.to_dict()
    assert d["visibility"] == "members"
    restored = Memory.from_dict(d)
    assert restored.visibility == "members"


def test_visibility_default_public():
    mem = Memory(target=date(2026, 4, 15), expires=date(2026, 4, 15), content="Event.")
    assert mem.visibility == "public"
    assert mem.to_dict()["visibility"] == "public"
