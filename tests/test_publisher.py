"""Tests for the publisher module."""

from datetime import date
from pathlib import Path

from memory import Memory
from publisher import generate_page, load_memories, main, _DEFAULT_TITLE


def _write_memory(
    path: Path,
    target: str,
    expires: str,
    content: str,
    title: str | None = None,
    time: str | None = None,
    place: str | None = None,
) -> None:
    mem = Memory(
        target=date.fromisoformat(target),
        expires=date.fromisoformat(expires),
        content=content,
        title=title,
        time=time,
        place=place,
    )
    mem.dump(path)


def test_load_memories_filters_expired(tmp_path: Path):
    _write_memory(tmp_path / "a.md", "2026-01-01", "2026-01-31", "January event")
    _write_memory(tmp_path / "b.md", "2026-03-01", "2026-06-01", "March event")
    _write_memory(tmp_path / "c.md", "2026-02-15", "2026-05-01", "February event")

    today = date(2026, 2, 18)
    memories = load_memories(tmp_path, today)

    assert len(memories) == 2
    assert memories[0].content == "February event"
    assert memories[1].content == "March event"


def test_load_memories_sorted_by_target(tmp_path: Path):
    _write_memory(tmp_path / "z.md", "2026-06-01", "2026-12-01", "June")
    _write_memory(tmp_path / "a.md", "2026-03-01", "2026-12-01", "March")

    memories = load_memories(tmp_path, date(2026, 1, 1))
    assert [m.content for m in memories] == ["March", "June"]


def test_generate_page_splits_this_week_and_future():
    # 2026-02-18 is a Wednesday; week ends Sunday 2026-02-22
    today = date(2026, 2, 18)
    memories = [
        Memory(target=date(2026, 2, 19), expires=date(2026, 3, 1),
               content="Thursday standup", title="Standup", time="10:00", place="Room A"),
        Memory(target=date(2026, 2, 22), expires=date(2026, 3, 1),
               content="Weekend brunch", title="Brunch", place="Cafe"),
        Memory(target=date(2026, 3, 5), expires=date(2026, 4, 1),
               content="March conference", title="Conference", time="09:00", place="Convention Center"),
    ]

    html = generate_page(memories, today)

    assert _DEFAULT_TITLE in html
    assert "This Week" in html
    assert "Upcoming" in html
    assert "Standup" in html
    assert "Room A" in html
    assert "10:00" in html
    assert "Brunch" in html
    assert "Conference" in html
    assert "Convention Center" in html
    # Content should be rendered as HTML (from markdown)
    assert "Thursday standup" in html
    assert "March conference" in html


def test_generate_page_no_events():
    html = generate_page([], date(2026, 2, 18))
    assert "No events." in html


def test_generate_page_renders_markdown_links():
    today = date(2026, 2, 18)
    memories = [
        Memory(target=date(2026, 2, 19), expires=date(2026, 3, 1),
               content="Details at [our site](https://example.com)",
               title="Bible Study"),
    ]
    html = generate_page(memories, today)
    assert '<a href="https://example.com">our site</a>' in html


def test_generate_page_renders_links_in_title():
    today = date(2026, 2, 18)
    memories = [
        Memory(target=date(2026, 2, 19), expires=date(2026, 3, 1),
               content="Join us for worship",
               title="[Sunday Service](https://example.com/service)"),
    ]
    html = generate_page(memories, today)
    assert '<a href="https://example.com/service">Sunday Service</a>' in html


def test_generate_page_event_without_title():
    today = date(2026, 2, 18)
    memories = [
        Memory(target=date(2026, 2, 19), expires=date(2026, 3, 1),
               content="Quick sync"),
    ]
    html = generate_page(memories, today)
    assert "Quick sync" in html


def test_main_end_to_end(tmp_path: Path):
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()
    _write_memory(
        mem_dir / "event.md", "2026-03-01", "2026-06-01",
        "Spring meetup", "Spring", time="14:00", place="Park",
    )

    out_dir = tmp_path / "site"

    main(["--memories-dir", str(mem_dir), "--output-dir", str(out_dir)])

    index = out_dir / "index.html"
    assert index.exists()
    content = index.read_text()
    assert "Spring" in content
    assert "Park" in content
    assert "14:00" in content
