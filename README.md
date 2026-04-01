# Small Group

Small Group is a Firebase- and Firestore-backed recurring-schedule platform with rooms, series, occurrences, check-ins, notifications, and an organizer assistant.

The current web app is deployed at `https://small-group.ai`.

## Architecture

### Backend

- `src/api.py` is the main FastAPI entry point (health check, middleware, mounts the v2 router).
- `src/api_v2.py` exposes the room, series, occurrence, check-in, notification, ICS, Telegram webhook, and assistant APIs.
- `src/db.py` provides the shared Firestore client factory.
- Firestore is the primary datastore.
- Firebase Auth provides user authentication for authenticated routes.
- Gemini powers the organizer assistant.

### Frontend

- `web/` is the primary React SPA, organized around rooms and recurring schedules.

### Domain Models

- `Room`
- `Series`
- `Occurrence`
- `CheckIn`
- `NotificationRule`
- `DeliveryLog`
- `study_assignment` series for practice-oriented check-ins

## Main User Flows

### Room and recurrence flow

1. Create a room.
2. Create one or more recurring series in that room.
3. Generate occurrences for a date window.
4. Edit, reschedule, complete, or cancel individual occurrences.
5. Record participant check-ins and configure notification rules.

### Organizer assistant flow

1. Send a message to the assistant endpoint for a room.
2. The assistant proposes a structured action.
3. The proposed action is stored as a pending action.
4. The user confirms or cancels it.
5. Confirmation executes the action against the room data.

## Local Development

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Python tests

```bash
.venv/bin/pytest
```

Run a single test:

```bash
.venv/bin/pytest tests/test_api_v2.py::TestSeriesEndpoints::test_create_series
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Required for AI-backed flows | Gemini API key |
| `GOOGLE_CLOUD_PROJECT` | Usually required outside tests | GCP project ID |
| `LIVING_MEMORY_FIRESTORE_DATABASE` | Optional | Firestore database name |
| `TELEGRAM_BOT_TOKEN` | Optional | Legacy Telegram adapter only; room bots are configured via the API |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Optional | Email notification delivery |
| `FROM_EMAIL` | Optional | Sender address for email notifications |
| `APP_BASE_URL` | Optional | Base URL used in links and ICS output |
| `WEBHOOK_BASE_URL` | Optional | Public HTTPS base URL for Telegram webhooks; overrides `APP_BASE_URL` for bot setup |

### Run the API locally

```bash
GEMINI_API_KEY=... \
  .venv/bin/uvicorn api:app --app-dir src --reload
```

### Run the React app locally

```bash
cd web
npm install
npm run dev
```

## Useful Commands

### Login CLI

```bash
login
login whoami
login token
login logout
```

## API Overview

Authenticated routes require a Firebase ID token in `Authorization: Bearer <token>`.

### API groups

- `/v2/rooms`
- `/v2/rooms/{room_id}/members`
- `/v2/rooms/{room_id}/series`
- `/v2/rooms/{room_id}/occurrences`
- `/v2/series/{series_id}`
- `/v2/series/{series_id}/occurrences`
- `/v2/occurrences/{occurrence_id}`
- `/v2/occurrences/{occurrence_id}/check-ins`
- `/v2/occurrences/{occurrence_id}/my-check-in`
- `/v2/rooms/{room_id}/notification-rules`
- `/v2/rooms/{room_id}/assistant`
- `/v2/assistant/actions/{action_id}/confirm`
- `/v2/assistant/actions/{action_id}/cancel`

### Example: create a room

```bash
curl -X POST https://small-group.ai/v2/rooms \
  -H "Authorization: Bearer $(login token)" \
  -H "Content-Type: application/json" \
  -d '{"title": "Weekly Standup", "type": "shared", "timezone": "America/New_York"}'
```

## Repository Layout

- `src/` Python backend
- `web/` React SPA
- `tests/` pytest suite
- `docs/design/` product and design docs for the room/series platform
- `scripts/` operational scripts
