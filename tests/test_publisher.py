"""Tests for the publisher module."""

from datetime import date
from pathlib import Path

from memory import Memory
from publisher import generate_page, _DEFAULT_TITLE, _render_event, _linkify_bare_urls, week_bounds


def test_generate_page_splits_this_week_and_future():
    # 2026-02-18 is a Wednesday; week is Sun Feb 15 – Sat Feb 21
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


def test_render_event_content_only():
    """Events with only content and target always render with a date in details."""
    mem = Memory(target=date(2026, 2, 19), expires=date(2026, 3, 1),
                 content="Simple announcement")
    html = _render_event(mem)
    assert "Simple announcement" in html
    assert "2026-02-19" in html


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


# --- week_bounds tests ---

def test_week_bounds_sunday():
    """On Sunday, the week starts today and ends Saturday."""
    # 2026-02-22 is a Sunday
    start, end = week_bounds(date(2026, 2, 22))
    assert start == date(2026, 2, 22)  # Sunday
    assert end == date(2026, 2, 28)    # Saturday


def test_week_bounds_wednesday():
    """On Wednesday, the week started last Sunday and ends this Saturday."""
    # 2026-02-18 is a Wednesday
    start, end = week_bounds(date(2026, 2, 18))
    assert start == date(2026, 2, 15)  # Sunday
    assert end == date(2026, 2, 21)    # Saturday


def test_week_bounds_saturday():
    """On Saturday, the week started last Sunday and ends today."""
    # 2026-02-21 is a Saturday
    start, end = week_bounds(date(2026, 2, 21))
    assert start == date(2026, 2, 15)  # Sunday
    assert end == date(2026, 2, 21)    # Saturday


def test_week_bounds_monday():
    """On Monday, the week started yesterday (Sunday)."""
    # 2026-02-23 is a Monday
    start, end = week_bounds(date(2026, 2, 23))
    assert start == date(2026, 2, 22)  # Sunday
    assert end == date(2026, 2, 28)    # Saturday


def test_this_week_resets_on_sunday():
    """On Sunday, prior-week events (Mon-Sat) should NOT appear in This Week."""
    # 2026-02-22 is a Sunday
    today = date(2026, 2, 22)
    memories = [
        # Last week events (Mon Feb 16 – Sat Feb 21)
        Memory(target=date(2026, 2, 16), expires=date(2026, 3, 1),
               content="Last Monday", title="Past Mon"),
        Memory(target=date(2026, 2, 21), expires=date(2026, 3, 1),
               content="Last Saturday", title="Past Sat"),
        # This week events (Sun Feb 22 – Sat Feb 28)
        Memory(target=date(2026, 2, 22), expires=date(2026, 3, 1),
               content="This Sunday", title="Today"),
        Memory(target=date(2026, 2, 25), expires=date(2026, 3, 1),
               content="This Wednesday", title="Wed"),
        # Future event
        Memory(target=date(2026, 3, 5), expires=date(2026, 4, 1),
               content="Next month", title="Future"),
    ]

    html = generate_page(memories, today)

    this_week_pos = html.index("This Week")
    upcoming_pos = html.index("Upcoming")

    # "Today" and "Wed" should be in This Week
    assert "Today" in html[this_week_pos:upcoming_pos]
    assert "Wed" in html[this_week_pos:upcoming_pos]

    # "Past Mon" and "Past Sat" should NOT be in This Week
    assert "Past Mon" not in html[this_week_pos:upcoming_pos]
    assert "Past Sat" not in html[this_week_pos:upcoming_pos]

    # "Future" should be in Upcoming
    assert "Future" in html[upcoming_pos:]
