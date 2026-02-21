"""Publisher — generates a static HTML page from memory files."""

from __future__ import annotations

import argparse
import re
from datetime import date, timedelta
from html import escape
from pathlib import Path

import markdown

from memory import Memory

_DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "page.html"
_DEFAULT_TITLE = "Our Church Events"


def load_memories(directory: Path, today: date, user_id: str | None = None) -> list[Memory]:
    """Load non-expired memories from *directory*, sorted by target date.

    If *user_id* is given, only memories belonging to that user are returned.
    """
    memories: list[Memory] = []
    for path in sorted(directory.glob("*.md")):
        mem = Memory.load(path)
        if mem.is_expired(today):
            continue
        if user_id is not None and mem.user_id != user_id:
            continue
        memories.append(mem)
    # Ongoing memories (no target) sort first so they appear at the top.
    memories.sort(key=lambda m: (m.target is not None, m.target or date.min))
    return memories


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
    return bool(mem.target or mem.time or mem.place
                or (mem.title and mem.content) or mem.attachments)


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


def generate_page(
    memories: list[Memory],
    today: date,
    *,
    template: str | None = None,
    site_title: str = _DEFAULT_TITLE,
) -> str:
    """Generate a complete HTML page with this-week and future sections."""
    if template is None:
        template = _DEFAULT_TEMPLATE.read_text()

    week_end = today + timedelta(days=(6 - today.weekday()))

    this_week = [m for m in memories if m.target is None or m.target <= week_end]
    future = [m for m in memories if m.target is not None and m.target > week_end]

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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate a static site from memories")
    parser.add_argument("--memories-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=None)
    parser.add_argument("--title", type=str, default=_DEFAULT_TITLE)
    parser.add_argument("--user-id", type=str, default=None,
                        help="Only render memories for this user (default: all)")
    args = parser.parse_args(argv)

    template_text = args.template.read_text() if args.template else None

    today = date.today()
    memories = load_memories(args.memories_dir, today, user_id=args.user_id)
    html = generate_page(memories, today, template=template_text, site_title=args.title)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index.html").write_text(html)


if __name__ == "__main__":
    main()
