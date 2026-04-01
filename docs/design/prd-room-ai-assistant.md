# PRD: Room AI Assistant via Telegram

**Status:** Draft
**Last updated:** 2026-04-01

---

## 1. Problem

Organizers need an easy way to manage their rooms — creating series, rescheduling, updating notes — without opening the app every time. The app already has an assistant backend (`assistant.py`) that can interpret natural language and propose actions, but it's only accessible through a basic in-app chat widget. Building a full chat UI with memory, streaming, and mobile support is too much work.

## 2. Insight

Telegram is already integrated as a notification channel. Every room could have its own Telegram bot that organizers chat with directly. This gives us a rich, native chat experience for free — with push notifications, mobile support, and group conversations — while we focus on the backend: scoping, safety, and memory.

## 3. Solution

Each room can optionally have a dedicated Telegram bot. An organizer creates a bot via BotFather, then configures the bot token in the app's room settings. The backend registers a webhook for that bot. Other organizers in the room can then message the bot in Telegram to manage the room's series.

### 3.1 Bot permission modes

Each bot is configured with a permission mode that controls what it can do:

**`read-only`** — The bot can answer questions but cannot change anything:
- List series, occurrences, and check-in status
- Answer "when's the next meeting?", "who's hosting Friday?", etc.
- Summarize the room's schedule

**`read-write`** — Everything in read-only, plus it can propose state changes:
- **Create a new series** (with confirm/cancel flow)
- **Reschedule an occurrence**
- **Update occurrence notes/agenda**
- **Draft meeting materials**
- **Generate reminder text**

The mode is set by the organizer when connecting the bot and can be changed at any time in room settings. All state-changing actions still require explicit confirmation via Telegram inline buttons.

**Implementation:** In read-only mode, the system prompt omits all action instructions, and the handler rejects any action payloads the AI might produce. In read-write mode, the full action system is available. This is enforced server-side — the mode is checked before calling the assistant and before executing any action.

### 3.2 What the bot cannot do (in any mode)

- Access any data outside its room
- Modify room membership or settings
- Execute actions without organizer confirmation
- Respond to users who are not organizers of the room

## 4. User Flow

### 4.1 Setup (one-time per room)

1. Organizer opens BotFather in Telegram, creates a new bot, gets a token
2. In the app, organizer goes to Room Settings > AI Assistant
3. Pastes the bot token, clicks "Connect"
4. Backend validates the token (calls Telegram `getMe`), registers a webhook, stores the bot config in a separate `telegram_bots` Firestore collection (not on the Room document — keeps secrets out of widely-read docs)
5. App shows the bot's Telegram username with a link to start chatting

### 4.2 Linking organizers (one-time per organizer)

1. In the app, organizer clicks "Generate Link Code" — backend creates a one-time 6-char code (expires in 5 minutes)
2. Organizer opens the bot in Telegram, sends `/link ABC123`
3. Bot verifies the code, associates the Telegram user ID with the app user ID
4. Bot confirms: "You're verified as [Name]. You can now manage [Room Title]."

Unlinked users who message the bot get: "Please link your account first. Go to Room Settings > AI Assistant in the app to get a link code, then send `/link <code>` here."

### 4.3 Daily use

1. Organizer messages the bot in Telegram: "Reschedule tomorrow's standup to 3pm"
2. Bot processes message through the assistant, proposes action with inline confirm/cancel buttons
3. Organizer taps "Confirm"
4. Bot executes the action and replies with confirmation

### 4.4 Slash commands

- `/start` — Welcome message with instructions
- `/link <code>` — Link Telegram account to app user
- `/help` — List available commands and example queries
- `/status` — Room overview (series count, next occurrence)
- `/reset` — Clear chat session history

## 5. Security Model

### 5.1 Room scoping

The AI is scoped at the **infrastructure level**, not just the prompt:

- Bot config lives in a separate `telegram_bots` collection, keyed by `bot_id`, linking to exactly one `room_id`
- When a webhook fires, the backend looks up `bot_id` → `room_id` from server state
- The assistant only receives context for that room — it physically cannot query other rooms
- The `room_id` is injected server-side, never from user input or AI output
- Even if the AI were tricked into outputting a different room_id, the action builder ignores it and uses the server-side room_id

### 5.2 Identity verification

- Organizers must link their Telegram account via the `/link` flow (see 4.2)
- Unlinked Telegram users get a polite "Please link your account first" response
- The link mapping is global (telegram_user_id → app_uid), but room membership is verified on every request
- Only users with the "organizer" role in the room can use the bot
- Participants cannot issue commands (but could potentially receive read-only info in a future phase)

### 5.3 Prompt injection defense

**Layer 1 — System prompt hardening:**
The system prompt explicitly instructs the AI to only operate within the room's scope and to ignore any embedded instructions in user messages.

**Layer 2 — Input sanitization:**
- Input length capped at 2000 characters
- Basic heuristic filtering for common injection patterns

**Layer 3 — Structural defense (most important):**
- The AI only produces structured JSON with a fixed schema — any malformed response is rejected
- All state-changing actions require explicit confirmation via Telegram inline buttons
- Action execution functions validate room_id ownership server-side
- The AI never sees bot tokens, other room IDs, or internal system details

**Layer 4 — Callback validation:**
- Telegram callback_data for confirm/cancel contains only the action_id
- On callback: verify the action exists, belongs to this room, and the clicking user is the requester

### 5.4 Rate limiting

- Per-chat: max 10 messages per minute
- Per-room: max 30 AI calls per hour
- Prevents abuse and controls Gemini API costs

## 6. Chat Memory

### 6.1 Storage

Chat history is stored in a top-level `chat_sessions` Firestore collection:

```
chat_sessions/{session_id}
```

Each session document:
```json
{
  "session_id": "...",
  "room_id": "...",
  "telegram_chat_id": "...",
  "app_uid": "...",
  "turns": [
    { "role": "user", "text": "...", "timestamp": "...", "action_id": null },
    { "role": "assistant", "text": "...", "timestamp": "...", "action_id": "uuid" }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

Session key: one session per `(room_id, telegram_chat_id)` pair.

### 6.2 Context window

- Last 20 turns are loaded and passed to the AI as conversation history
- Older turns are kept for audit but not included in the prompt
- Sessions can be reset with `/reset` command
- Sessions inactive for 24+ hours start with fresh context

### 6.3 Room context injection

Each AI call also receives a snapshot of the room's current state:
- Room title, description, timezone
- Active series (titles, schedules, next occurrence)
- Upcoming occurrences (next 7 days)

This is the same `room_context` dict already used by `assistant.py`.

## 7. Data Model

### 7.1 New collection: `telegram_bots`

Bot config lives in its own collection, NOT on the Room document. This keeps secrets isolated from the widely-read Room document.

```python
BotMode = Literal["read_only", "read_write"]

@dataclass
class TelegramBotConfig:
    bot_id: str              # Telegram bot user ID (from getMe) — doc ID
    room_id: str             # FK to workspaces collection
    bot_token: str           # encrypted at rest
    bot_username: str        # e.g. "MyMeetingBot"
    webhook_secret: str      # auto-generated per bot
    mode: BotMode = "read_only"  # permission mode
    created_by: str          # UID of organizer who configured it
    active: bool = True
    created_at: datetime
    updated_at: datetime
```

One bot per room (enforced at creation time).

### 7.2 New collection: `telegram_links`

Global mapping from Telegram user to app user. Room membership is verified at request time.

```python
@dataclass
class TelegramUserLink:
    telegram_user_id: str    # doc ID
    app_uid: str             # Firebase UID
    display_name: str
    linked_at: datetime
```

### 7.3 New collection: `chat_sessions`

See section 6.1.

### 7.4 New collection: `telegram_link_codes`

Ephemeral codes for the linking flow:

```json
{
  "code": "ABC123",
  "room_id": "...",
  "app_uid": "...",
  "expires_at": "..."
}
```

### 7.5 Room model — no changes

Bot config is separate. The Room model stays clean.

## 8. API Changes

### 8.1 Bot configuration (authenticated, organizer-only)

```
POST   /v2/rooms/{room_id}/telegram-bot
Body: { "bot_token": "...", "mode": "read_only" | "read_write" }
→ Validates token (getMe), registers webhook, stores config
→ Returns: { "bot_id": "...", "bot_username": "...", "mode": "...", "active": true }
→ Never returns bot_token

PATCH  /v2/rooms/{room_id}/telegram-bot
Body: { "mode": "read_write" }
→ Updates bot permission mode
→ Returns updated config (without token)

GET    /v2/rooms/{room_id}/telegram-bot
→ Returns bot config without token, or 404

DELETE /v2/rooms/{room_id}/telegram-bot
→ Calls deleteWebhook, removes config and links
```

### 8.2 Link code generation (authenticated, organizer-only)

```
POST   /v2/rooms/{room_id}/telegram-bot/link-code
→ Generates 6-char code, stores with 5-minute TTL
→ Returns: { "code": "ABC123", "expires_in": 300 }
```

### 8.3 Webhook endpoint (per-bot)

```
POST   /v2/channels/telegram/webhook/{bot_id}
→ Validates per-bot webhook_secret from X-Telegram-Bot-Api-Secret-Token header
→ Routes to correct room's assistant
```

Replaces the current global webhook. Old endpoint kept during transition.

## 9. New Backend Modules

### 9.1 `src/telegram_storage.py`

CRUD for `telegram_bots`, `telegram_links`, `chat_sessions`, and `telegram_link_codes` collections.

### 9.2 `src/telegram_chat_handler.py`

Main handler for incoming Telegram messages:

1. Look up `bot_id` → room config
2. Parse update (text message or callback query)
3. For callbacks: verify action ownership, execute or cancel, reply
4. For `/link`: redeem code, create user link
5. For free text: verify identity → load session → build room context → call assistant → send response with inline buttons if action proposed → save turns

## 10. Implementation Phases

### Phase 1: Bot registration and webhook routing
- `TelegramBotConfig` dataclass and storage
- API endpoints to register/unregister bot (POST/GET/DELETE)
- New parameterized webhook endpoint
- Basic echo response to verify the pipeline works

### Phase 2: Identity linking
- `TelegramUserLink` dataclass and storage
- Link code generation/redemption
- `/start` and `/link` command handlers
- Organizer role verification on every message

### Phase 3: Chat memory and assistant integration
- `ChatSession`/`ChatTurn` dataclasses and storage
- Load last 20 turns as conversation history
- Wire up `run_assistant_stream` with room context
- Reply via Telegram `sendMessage`
- Save turns after each exchange

### Phase 4: Action confirmation via inline buttons
- Send Telegram inline keyboards for proposed actions
- Handle callback queries for confirm/cancel
- Call existing `execute_action` / `update_pending_action_status`
- Send result messages

### Phase 5: Security hardening
- Bot token encryption (AES-256 with env var key, migrate to KMS later)
- Enhanced system prompt with injection defenses
- Input sanitization layer
- Rate limiting (per-chat and per-room)
- Audit logging

### Phase 6: App UI
- Room settings: "AI Assistant" section with bot token input
- Connected bot status display with Telegram link
- Link code generation button
- Delete bot button
- Both web (React) and mobile (Flutter)

## 11. Open Questions

1. **One bot per room vs. shared bot?** This PRD assumes one bot per room (organizer creates it). Alternative: a single app-wide bot that organizers `/connect` to a room. Simpler setup but less isolation. **Current recommendation: one bot per room for stronger scoping.**

2. **Group chats?** Should the bot work in Telegram group chats (multiple organizers in one chat) or only 1:1 DMs? Group chats are more collaborative but harder to scope identity. **Current recommendation: private chats only in Phase 1.**

3. **Bot token security.** Start with AES encryption in Firestore using an env var key. Migrate to Google Secret Manager if needed. Never return tokens in API responses.

4. **Cost control.** Each message triggers a Gemini API call. Use `gemini-2.5-flash-lite` (cheap), limit history to 20 turns, enforce per-room rate limits. Consider usage dashboard later.

5. **Participant access.** Should participants (non-organizers) be able to query the bot for read-only info like "when's the next meeting"? **Current recommendation: organizer-only in Phase 1, consider read-only participant access later.**

6. **Existing global Telegram webhook.** Migration is complete. The old `POST /v2/channels/telegram/webhook` path is now retired, and room bots use `POST /v2/channels/telegram/webhook/{bot_id}` instead. The old adapter remains only as legacy code and should not be used for new setup.
