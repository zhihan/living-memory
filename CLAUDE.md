# CLAUDE.md

This file gives repo-specific guidance for coding agents working in this repository.

## Project Overview

Event Ledger is a recurring-schedule platform built on Firebase and Firestore. The core domain includes `Workspace`, `Series`, `Occurrence`, `CheckIn`, notification, study/cohort, and assistant flows.

## Primary Runtime Surfaces

- `src/api.py`
  Main FastAPI entry point: health check, middleware, mounts the v2 router.
- `src/api_v2.py`
  FastAPI surface for workspaces, membership, recurring series, occurrences, check-ins, notifications, cohorts, ICS export, Telegram webhook handling, and assistant actions.
- `web/`
  Primary React SPA with workspace-centric routes.

## Core Backend Modules

- `src/models.py`
  Canonical dataclasses for `Workspace`, `Series`, `Occurrence`, `CheckIn`, `NotificationRule`, and `DeliveryLog`.
- `src/db.py`
  Shared Firestore client factory.
- `src/recurrence.py`
  Pure recurrence engine for generating UTC occurrence timestamps from schedule rules.
- `src/occurrence_service.py`
  Service layer bridging recurrence generation with Firestore persistence.
- `src/assistant.py`
  Organizer assistant orchestration.
- `src/assistant_actions.py`
  Pending-action storage plus confirm/cancel/execute flow.

## Storage Modules

- `src/workspace_storage.py`
  Workspace and membership storage.
- `src/series_storage.py`
  Series, occurrence, check-in, notification rule, and delivery log storage.
- `src/study_storage.py`
  Cohort, badge, and streak snapshot storage.
- `src/delivery_storage.py`
  Delivery log queries for the notification scheduler.

## Development

Setup:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Run all tests:

```bash
.venv/bin/pytest
```

Run the API locally:

```bash
GEMINI_API_KEY=... \
  .venv/bin/uvicorn api:app --app-dir src --reload
```

Run the React app:

```bash
cd web
npm install
npm run dev
```

### Flutter Mobile App

Setup:

```bash
cd flutter_app
flutter pub get
```

Run model/unit tests (no simulator needed):

```bash
cd flutter_app
dart test test/models/ test/shared/ test/widget_test.dart
```

Run all tests including widget tests (needs Flutter SDK with simulator):

```bash
cd flutter_app
flutter test
```

Run the app on a simulator:

```bash
cd flutter_app
flutter run
```

Before first run, generate Firebase config:

```bash
cd flutter_app
flutterfire configure --project=living-memories-488001
```

## Authentication

Authenticated API routes use Firebase ID tokens. For local manual testing, use:

```bash
login
login token
login whoami
login logout
```

## Documentation Guidance

Prefer keeping these docs aligned with the actual code instead of historical plans:

- `README.md` should describe the repository as it exists now.
- Historical issue plans that no longer match the code should be removed rather than left as if they were current.
- Product-level docs under `docs/design/` may remain if they still describe the active direction of the project.
