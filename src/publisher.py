"""Publisher — generates a static HTML page from memory files."""

from __future__ import annotations

import argparse
import re
from datetime import date, timedelta
from html import escape
from pathlib import Path

import markdown

from dates import today as _today
from memory import Memory

_DEFAULT_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ site_title }}</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
  h1 { border-bottom: 2px solid #333; padding-bottom: 0.5rem; }
  h2 { color: #555; }
  ul { list-style: none; padding: 0; }
  li { margin-bottom: 1rem; padding: 0.75rem; background: #f8f8f8; border-radius: 6px; }
  details summary { cursor: pointer; }
  details summary strong { display: inline; }
</style>
</head>
<body>
<h1>{{ site_title }}</h1>
{{ this_week }}
{{ upcoming }}
</body>
</html>
"""
_DEFAULT_TITLE = "Our Church Events"


def _attachment_label(url: str) -> str:
    """Derive a human-readable label from an attachment URL."""
    from urllib.parse import urlparse, unquote
    path = unquote(urlparse(url).path)
    name = path.rsplit("/", 1)[-1] if "/" in path else path
    return name or "attachment"


_BARE_URL_RE = re.compile(
    r"(?<![(<\"'])"   # not preceded by ( < " ' (already in a link)
    r"(https?://\S+)"
)


def _linkify_bare_urls(text: str) -> str:
    """Wrap bare URLs in angle brackets so markdown renders them as links."""
    return _BARE_URL_RE.sub(r"<\1>", text)


def _md_inline(text: str) -> str:
    """Render markdown but strip the wrapping <p> tag for inline use."""
    html = markdown.markdown(_linkify_bare_urls(text))
    if html.startswith("<p>") and html.endswith("</p>"):
        html = html[3:-4]
    return html


def _has_details(mem: Memory) -> bool:
    """Return True if the memory has detail content beyond the title."""
    return bool(mem.time or mem.place or (mem.title and mem.content) or mem.attachments)


def _render_event(mem: Memory) -> str:
    """Render a single memory as an HTML list item.

    When the event has extra details (date, time, place, body, or
    attachments) they are wrapped in a ``<details>`` element so the
    reader can expand/collapse them.
    """
    title_html = _md_inline(mem.title or mem.content)

    detail_parts: list[str] = []
    meta = [str(mem.target)] if mem.target else []
    if mem.time:
        meta.append(escape(mem.time))
    if mem.place:
        meta.append(escape(mem.place))
    if meta:
        detail_parts.append(f"<p>{' · '.join(meta)}</p>")
    if mem.title and mem.content:
        content_html = markdown.markdown(_linkify_bare_urls(mem.content))
        detail_parts.append(f"<div>{content_html}</div>")
    if mem.attachments:
        links = " ".join(
            f'<a href="{escape(url)}">{escape(_attachment_label(url))}</a>'
            for url in mem.attachments
        )
        detail_parts.append(f'<div class="attachments">Attachments: {links}</div>')

    if detail_parts:
        inner = "\n".join(detail_parts)
        return (
            f"<li><details>\n"
            f"<summary><strong>{title_html}</strong></summary>\n"
            f"{inner}\n"
            f"</details></li>"
        )
    return f"<li><strong>{title_html}</strong></li>"


def week_bounds(today: date) -> tuple[date, date]:
    """Return (week_start, week_end) for a Sunday-to-Saturday week.

    *week_start* is the most recent Sunday (<= today) and *week_end* is the
    following Saturday.  On Sunday itself, week_start == today.
    """
    # date.isoweekday(): Mon=1 … Sun=7
    days_since_sunday = today.isoweekday() % 7  # Sun→0, Mon→1, …, Sat→6
    week_start = today - timedelta(days=days_since_sunday)
    week_end = week_start + timedelta(days=6)  # Saturday
    return week_start, week_end


def generate_page(
    memories: list[Memory],
    today: date,
    *,
    template: str | None = None,
    site_title: str = _DEFAULT_TITLE,
) -> str:
    """Generate a complete HTML page with this-week and future sections."""
    if template is None:
        template = _DEFAULT_TEMPLATE

    week_start, week_end = week_bounds(today)

    this_week = [m for m in memories if week_start <= m.target <= week_end]
    future = [m for m in memories if m.target > week_end]

    def render_section(title: str, events: list[Memory]) -> str:
        if not events:
            return f"<h2>{title}</h2>\n<p>No events.</p>"
        items = "\n".join(_render_event(e) for e in events)
        return f"<h2>{title}</h2>\n<ul>\n{items}\n</ul>"

    this_week_html = render_section("This Week", this_week)
    future_html = render_section("Upcoming", future)

    return (
        template
        .replace("{{ site_title }}", escape(site_title))
        .replace("{{ this_week }}", this_week_html)
        .replace("{{ upcoming }}", future_html)
    )


def load_memories_from_firestore(today: date) -> list[Memory]:
    """Load non-expired memories from Firestore, sorted by target date."""
    import firestore_storage

    pairs = [
        (did, mem) for did, mem in firestore_storage.load_all_memories()
        if not mem.is_expired(today)
    ]

    memories = [mem for _, mem in pairs]
    memories.sort(key=lambda m: m.target)
    return memories


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate a static site from memories")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=None)
    parser.add_argument("--title", type=str, default=_DEFAULT_TITLE)
    args = parser.parse_args(argv)

    template_text = args.template.read_text() if args.template else None

    today = _today()
    memories = load_memories_from_firestore(today)

    html = generate_page(memories, today, template=template_text, site_title=args.title)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index.html").write_text(html)


if __name__ == "__main__":
    main()
