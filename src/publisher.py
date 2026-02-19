"""Publisher — generates a static HTML page from memory files."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from html import escape
from pathlib import Path

import markdown

from memory import Memory

_DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "page.html"
_DEFAULT_TITLE = "Church in Cambridge Events"


def load_memories(directory: Path, today: date) -> list[Memory]:
    """Load non-expired memories from *directory*, sorted by target date."""
    memories: list[Memory] = []
    for path in sorted(directory.glob("*.md")):
        mem = Memory.load(path)
        if not mem.is_expired(today):
            memories.append(mem)
    memories.sort(key=lambda m: m.target)
    return memories


def _md_inline(text: str) -> str:
    """Render markdown but strip the wrapping <p> tag for inline use."""
    html = markdown.markdown(text)
    if html.startswith("<p>") and html.endswith("</p>"):
        html = html[3:-4]
    return html


def _render_event(mem: Memory) -> str:
    """Render a single memory as an HTML list item."""
    title_html = _md_inline(mem.title or mem.content)
    parts = [f"<li><strong>{title_html}</strong>"]
    details = [str(mem.target)]
    if mem.time:
        details.append(escape(mem.time))
    if mem.place:
        details.append(escape(mem.place))
    if details:
        parts.append(f"<br>{' · '.join(details)}")
    if mem.title and mem.content:
        content_html = markdown.markdown(mem.content)
        parts.append(f"<div>{content_html}</div>")
    parts.append("</li>")
    return "\n".join(parts)


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

    this_week = [m for m in memories if m.target <= week_end]
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate a static site from memories")
    parser.add_argument("--memories-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=None)
    parser.add_argument("--title", type=str, default=_DEFAULT_TITLE)
    args = parser.parse_args(argv)

    template_text = args.template.read_text() if args.template else None

    today = date.today()
    memories = load_memories(args.memories_dir, today)
    html = generate_page(memories, today, template=template_text, site_title=args.title)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index.html").write_text(html)


if __name__ == "__main__":
    main()
