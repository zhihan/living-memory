"""Tests for the publisher module."""

from datetime import date
from pathlib import Path

from memory import Memory
from publisher import generate_page, load_memories, main, _DEFAULT_TITLE, _render_event, _linkify_bare_urls


def _write_memory(
    path: Path,
    target: str | None,
    expires: str,
    content: str,
    title: str | None = None,
    time: str | None = None,
    place: str | None = None,
) -> None:
    mem = Memory(
        target=date.fromisoformat(target) if target else None,
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


def test_load_memories_keeps_ongoing(tmp_path: Path):
    """Ongoing memories (no target) are never filtered out before expiry."""
    _write_memory(tmp_path / "ongoing.md", None, "2026-03-01", "Weekly event", title="Worship")
    _write_memory(tmp_path / "expired.md", "2026-01-01", "2026-01-31", "Old event")

    memories = load_memories(tmp_path, date(2026, 2, 18))
    assert len(memories) == 1
    assert memories[0].title == "Worship"
    assert memories[0].target is None


def test_generate_page_ongoing_in_this_week():
    """Ongoing memories appear in the This Week section."""
    today = date(2026, 2, 18)
    memories = [
        Memory(target=None, expires=date(2026, 2, 22),
               content="Every Sunday", title="Worship", time="10:00"),
        Memory(target=date(2026, 3, 5), expires=date(2026, 4, 1),
               content="Future event", title="Conference"),
    ]
    html = generate_page(memories, today)
    # Worship should be in This Week, Conference in Upcoming
    this_week_pos = html.index("This Week")
    upcoming_pos = html.index("Upcoming")
    worship_pos = html.index("Worship")
    conference_pos = html.index("Conference")
    assert this_week_pos < worship_pos < upcoming_pos
    assert upcoming_pos < conference_pos


def test_generate_page_renders_attachments():
    """Attachments are rendered as links."""
    today = date(2026, 2, 18)
    memories = [
        Memory(target=date(2026, 2, 19), expires=date(2026, 3, 1),
               content="See flyer", title="Event",
               attachments=["https://storage.googleapis.com/bucket/flyer.pdf"]),
    ]
    html = generate_page(memories, today)
    assert "Attachments:" in html
    assert 'href="https://storage.googleapis.com/bucket/flyer.pdf"' in html
    assert "flyer.pdf" in html


def test_generate_page_no_attachments_no_section():
    """No attachments div when memory has no attachments."""
    today = date(2026, 2, 18)
    memories = [
        Memory(target=date(2026, 2, 19), expires=date(2026, 3, 1),
               content="No files", title="Event"),
    ]
    html = generate_page(memories, today)
    assert "Attachments:" not in html


def test_render_event_uses_details_element():
    """Events with details are wrapped in a <details>/<summary> element."""
    mem = Memory(target=date(2026, 2, 19), expires=date(2026, 3, 1),
                 content="Come join us", title="Gathering",
                 time="10:00", place="Room A")
    html = _render_event(mem)
    assert "<details>" in html
    assert "<summary>" in html
    assert "</details>" in html
    assert "Gathering" in html
    assert "10:00" in html
    assert "Room A" in html
    assert "Come join us" in html


def test_render_event_no_details_no_fold():
    """Events without extra details render without a <details> element."""
    mem = Memory(target=None, expires=date(2026, 3, 1),
                 content="Simple announcement")
    html = _render_event(mem)
    assert "<details>" not in html
    assert "Simple announcement" in html


def test_generate_page_linkifies_bare_urls():
    """Bare URLs (e.g. Zoom links with query params) become clickable <a> links."""
    today = date(2026, 2, 18)
    zoom_url = "https://us02web.zoom.us/j/5474967529?pwd=L2V6T0xRUGpwYTV2bUgvU08xalRUUT09"
    memories = [
        Memory(
            target=date(2026, 2, 21),
            expires=date(2026, 3, 23),
            content=f"Join Zoom Meeting\n\n{zoom_url}\n\nMeeting ID: 547 496 7529",
            title="Online Revival",
            time="8:30",
            place="Zoom",
        ),
    ]
    html = generate_page(memories, today)
    assert f'href="{zoom_url}"' in html
    assert f">{zoom_url}</a>" in html


def test_linkify_bare_urls_preserves_markdown_links():
    """URLs already in markdown link syntax are not double-wrapped."""
    text = "Visit [our site](https://example.com) for details"
    result = _linkify_bare_urls(text)
    assert "](https://example.com)" in result
    assert "<https://example.com>" not in result


def test_linkify_bare_urls_wraps_bare():
    """A bare URL gets wrapped in angle brackets."""
    text = "Join at https://zoom.us/j/123?pwd=abc"
    result = _linkify_bare_urls(text)
    assert "<https://zoom.us/j/123?pwd=abc>" in result


def test_load_memories_filters_by_user_id(tmp_path: Path):
    """When user_id is given, only that user's memories are loaded."""
    Memory(target=date(2026, 3, 1), expires=date(2026, 6, 1),
           content="Alice event", title="Alice", user_id="alice").dump(
        tmp_path / "alice.md")
    Memory(target=date(2026, 3, 2), expires=date(2026, 6, 1),
           content="Bob event", title="Bob", user_id="bob").dump(
        tmp_path / "bob.md")

    alice_mems = load_memories(tmp_path, date(2026, 2, 18), user_id="alice")
    assert len(alice_mems) == 1
    assert alice_mems[0].title == "Alice"

    all_mems = load_memories(tmp_path, date(2026, 2, 18))
    assert len(all_mems) == 2
