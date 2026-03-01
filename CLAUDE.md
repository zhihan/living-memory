# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Event Ledger is a static website generator similar to a CMS. It uses **Firestore** (Google Cloud Firestore) for memory storage and **Firebase Auth** for authentication.

## Architecture

The system has two independent components that do not necessarily run on the same machine:

- **Committer** — A conversational agent that chats with the user. When the user asks it to memorize something, it examines the existing memory, deduplicates, updates the memory with the new information, and saves to Firestore. The core logic is exposed as `commit_memory_firestore()` for programmatic use by the API.
- **HTTP API** — A FastAPI app (`src/api.py`) deployed to Cloud Run. Provides REST endpoints for managing pages, memories, invites, and users via Firestore. Uses Firebase Auth (ID tokens).
- **Publisher** — Reads memories from Firestore, generates a static HTML page with two sections (this week's events and upcoming events), and deploys to GitHub Pages.

The flow: User → Committer/API → Firestore ← client/index.html (GitHub Pages).

## Memory Format

Each memory is a Firestore document. Required fields:
- `target` — date the event occurs (ISO 8601), or null for ongoing events
- `expires` — date when the memory can safely be removed

Optional fields:
- `title` — short event name
- `time` — time of day (free-form string, e.g. "10:00")
- `place` — location of the event

The core data structure is `Memory` in `src/memory.py`. It supports `to_dict()`/`from_dict()` for Firestore serialization.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Run all tests:
```bash
.venv/bin/pytest
```

Run a single test:
```bash
.venv/bin/pytest tests/test_memory.py::test_name
```

## Committer

Add or update a memory using natural language (requires `GEMINI_API_KEY` env var):
```bash
GEMINI_API_KEY=... .venv/bin/python -m committer \
  --message "Team meeting next Thursday at 10am in Room A"
```

Use `--today 2026-02-18` to override today's date (useful for testing).

The AI reads existing memories and decides whether to create a new one or update an existing one.

## Publisher

Generate a static site:
```bash
.venv/bin/python -m publisher --output-dir site/
```

In CI, the publisher runs automatically via `.github/workflows/publish.yml`.

## Cleanup

Remove expired memories from Firestore:
```bash
.venv/bin/python -m cleanup
```

## Login (CLI Authentication)

Authenticate with Firebase via browser-based Google OAuth:
```bash
login              # opens browser, stores credentials in system keyring
login whoami       # print the logged-in email
login token        # print a fresh ID token (for curl)
login logout       # clear stored credentials
```

Use the token with the API:
```bash
curl -H "Authorization: Bearer $(login token)" https://...
```

## HTTP API

Run locally:
```bash
GEMINI_API_KEY=... \
  .venv/bin/uvicorn api:app --app-dir src --reload
```

Endpoints:
- `GET /_healthz` — health check (legacy alias `GET /healthz` also works)
- `POST /pages` — create a page (Firebase Auth)
- `GET /pages/{slug}` — get page metadata
- `PATCH /pages/{slug}` — rename / update page metadata (Firebase Auth)
- `DELETE /pages/{slug}` — soft-delete a page with 30-day grace period (Firebase Auth)
- `POST /pages/{slug}/restore` — restore a soft-deleted page (Firebase Auth)
- `POST /pages/{slug}/memories` — create a memory on a page (Firebase Auth)
- `GET /pages/{slug}/memories` — list memories for a page
- `DELETE /pages/{slug}/memories/{id}` — delete a memory (Firebase Auth)
- `POST /pages/{slug}/invites` — create an invite link (Firebase Auth)
- `POST /invites/{id}/accept` — accept an invite (Firebase Auth)
- `GET /users/me` — get current user (Firebase Auth)
- `GET /users/me/pages` — list pages owned by current user (Firebase Auth)

Deployed to Cloud Run via `.github/workflows/deploy-api.yml`.

## Client-Side Page

A static HTML page (`client/index.html`) that reads Firestore directly in the browser using the Firebase Web SDK. No server required — deploy to GitHub Pages or open locally. Supports `?user_id=...` query parameter (default: `cambridge-lexington`).

## Repository Structure

- `client/` - Client-side Firestore reader (static HTML/JS)
- `src/` - Python source code
  - `memory.py` — core Memory dataclass with to_dict/from_dict/expiry
  - `firestore_storage.py` — Firestore CRUD: save, load, delete, find_by_title, delete_expired
  - `committer.py` — CLI + core `commit_memory_firestore()` function for adding/updating memories
  - `api.py` — FastAPI HTTP API for Cloud Run (Firebase Auth, page-scoped endpoints)
  - `cleanup.py` — delete expired memories from Firestore and purge GCS attachments
  - `publisher.py` — static site generator (load memories from Firestore → HTML with this-week/upcoming sections)
  - `storage.py` — GCS upload/delete helpers for file attachments
  - `login.py` — CLI login command: browser OAuth flow, keyring storage, token refresh
  - `page_storage.py` — Firestore CRUD for pages, invites, users, and audit logs
- `templates/` - HTML template for site layout
- `tests/` - Pytest test suite (Firestore mocked in tests)
- `Dockerfile` - Container image for Cloud Run API deployment
- `.github/workflows/` - CI/CD (publish on push, deploy API to Cloud Run)
