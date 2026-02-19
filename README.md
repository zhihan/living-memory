# Living Memory

A static website generator with no database. The "database" is an organized collection of markdown files stored in a git repo.

## How It Works

1. **Committer** — CLI tool that adds event memories to the repo and pushes to GitHub.
2. **Publisher** — GitHub Actions workflow that generates a static HTML page and deploys to GitHub Pages.

```
User → committer → git push → GitHub Actions → publisher → static site
```

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Add a memory

Requires `GEMINI_API_KEY`. Set it in a `.env` file at the project root or as an environment variable.

```bash
.venv/bin/python -m committer --message "Team meeting next Thursday at 10am in Room A"
```

Options:
- `--memories-dir` — directory for memory files (default: `memories/`)
- `--no-push` — skip git push
- `--today 2026-02-18` — override today's date (for testing)

The AI extracts event details from your message and decides whether to create a new memory or update an existing one.

### Generate the site locally

```bash
python -m publisher --memories-dir memories/ --output-dir site/
```

The output is a single `index.html` with two sections: **This Week** and **Upcoming**.

## Memory Format

Each memory is a markdown file with YAML frontmatter:

```markdown
---
target: 2026-03-01
expires: 2026-04-01
title: Team Meeting
time: "10:00"
place: Room A
---
Weekly planning session.
```

Required fields: `target`, `expires`. Optional: `title`, `time`, `place`.

## Running Tests

```bash
.venv/bin/pytest
```
