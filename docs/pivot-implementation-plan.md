# Implementation Plan: Pivot to Study, Reminder, and Meeting Assistant

## 1. Goal

Rework the current Event Ledger codebase into a recurring-schedule platform that supports:

1. personal reminders
2. shared meeting coordination
3. supervised study

The implementation should preserve and reuse what already exists:

- Firebase Auth
- FastAPI backend
- Firestore-backed storage
- role-aware page and membership patterns
- React web app shell

The implementation should retire or de-emphasize what no longer fits:

- static publisher flow
- page-centric naming
- memory-as-the-primary-domain-object

Initial delivery constraints:

- mobile web app only
- Google sign-in only
- no native mobile clients in phase 1

---

## 2. Current Assets We Can Reuse

### 2.1 Backend

- [src/api.py](/Users/zhih/projects/event-ledger/src/api.py): authenticated API scaffold, routing, middleware, logging
- [src/page_storage.py](/Users/zhih/projects/event-ledger/src/page_storage.py): Firestore patterns for pages, users, roles, invites, audit logs
- [src/firestore_storage.py](/Users/zhih/projects/event-ledger/src/firestore_storage.py): Firestore client and simple CRUD patterns
- [src/dates.py](/Users/zhih/projects/event-ledger/src/dates.py): timezone resolution

### 2.2 Frontend

- [web/src/main.tsx](/Users/zhih/projects/event-ledger/web/src/main.tsx): React SPA entry and routing
- [web/src/auth.tsx](/Users/zhih/projects/event-ledger/web/src/auth.tsx): auth context and protected-route pattern
- [web/src/api.ts](/Users/zhih/projects/event-ledger/web/src/api.ts): authenticated API client
- dashboard and page views can be repurposed into workspace and series views

### 2.3 AI and integrations

- [src/committer.py](/Users/zhih/projects/event-ledger/src/committer.py): existing AI integration, streaming pattern, and user-message parsing workflow
- [src/storage.py](/Users/zhih/projects/event-ledger/src/storage.py): attachment upload pattern if meeting materials need files later

---

## 3. Architectural Refactor Direction

### 3.1 Rename the core concepts

Move from:

- page
- memory

To:

- workspace
- series
- occurrence
- check_in
- content_packet

### 3.2 Keep the app layered

- React web app for end-user UI
- FastAPI API for all business rules
- Firestore for document storage
- background job or task runner for notification dispatch and occurrence generation
- optional chat assistants as separate adapters on top of the same API

### 3.3 Avoid embedding channel-specific logic in core product flows

Build a notification abstraction early:

- notification target
- notification channel
- delivery template
- delivery log

Then add email, calendar, Telegram, and later WhatsApp or WeChat as adapters.

---

## 4. Recommended Delivery Strategy

Do this in phases. Do not attempt all three use cases at once.

Recommended order:

1. Build the recurrence engine in service of organizer-run meeting coordination
2. Add personal reminders on top of the same engine
3. Add supervised study on top of the same occurrence and check-in model
4. Add external assistant and messaging integrations after the core data model is stable

Reason:

- recurrence plus editable occurrences is the hardest core problem
- meetings and supervised study both depend on the same scheduling foundation
- external channel work adds operational complexity and should not define the data model prematurely
- staying on mobile web plus Google auth lets us reuse the current React and Firebase stack with minimal auth churn
- meeting organizers provide a stronger and more differentiated initial use case

---

## 5. Implementation Phases

## Phase 0: Product narrowing and naming

Objective:

- commit to the vocabulary and MVP boundary before rewriting the backend

Tasks:

- choose the MVP wedge:
  - meeting organizers first
- define final product and object names
- commit to mobile web as the only client platform for MVP
- commit to Google as the only login provider for MVP
- commit to organizer-only mode for the first shipped workflow
- decide what remains from the old page model versus what gets replaced

Deliverables:

- approved PRD
- approved MVP scope
- naming map from old model to new model
- explicit confirmation that meeting organizer workflow is the first shipped use case
- explicit confirmation that only organizers need accounts in MVP

## Phase 1: Data model redesign

Objective:

- create the foundational recurrence-aware domain model

New collections:

- `workspaces`
- `workspace_members`
- `series`
- `occurrences`
- `check_ins`
- `notification_rules`
- `delivery_logs`

Optional later collections:

- `content_packets`
- `assistant_threads`
- `badges`

Core schema:

- `Workspace`
  - `id`
  - `type`
  - `title`
  - `timezone`
  - `owner_uids`
  - `member_roles`
- `Series`
  - `workspace_id`
  - `kind`: reminder, meeting, study_assignment
  - `title`
  - `schedule_rule`
  - `default_time`
  - `default_location`
  - `default_online_link`
  - `status`
- `Occurrence`
  - `series_id`
  - `scheduled_for`
  - `status`
  - `overrides`
  - `content_packet_id`
- `CheckIn`
  - `occurrence_id`
  - `user_id`
  - `status`
  - `checked_in_at`

Tasks:

- add new domain models in `src/`
- add Firestore storage modules for new entities
- keep old modules temporarily for migration compatibility
- design recurrence serialization format

Deliverables:

- domain dataclasses or models
- storage CRUD
- migration strategy from `pages` and `memories`

## Phase 2: Recurrence engine and occurrence exceptions

Objective:

- support recurring schedules and editable single instances

Tasks:

- implement recurrence rules:
  - daily
  - weekly
  - weekdays
  - selected weekdays
- implement occurrence generation window
- implement single-occurrence override model
- support skip, reschedule, complete, and edit-one-instance
- ensure timezone-aware generation

Suggested module additions:

- `src/recurrence.py`
- `src/series_storage.py`
- `src/occurrence_storage.py`

Deliverables:

- deterministic recurrence engine
- tests for recurrence and exceptions
- admin-safe regeneration logic

## Phase 3: API v2 for workspaces, series, occurrences, and check-ins

Objective:

- expose the new product model without breaking the existing app during migration

Tasks:

- add new endpoints under a clean namespace, for example:
  - `POST /workspaces`
  - `GET /workspaces/{id}`
  - `POST /workspaces/{id}/series`
  - `GET /workspaces/{id}/occurrences`
  - `PATCH /occurrences/{id}`
  - `POST /occurrences/{id}/check-ins`
- keep auth and audit logging patterns from current API
- enforce role-based permissions:
  - organizer
  - participant
  - teacher
  - assistant
  - student

Deliverables:

- v2 API surface
- role enforcement
- integration tests

## Phase 4: Web app pivot

Objective:

- replace the page-centric UI with workspace and schedule workflows

Tasks:

- rename dashboard concepts from pages to workspaces
- redesign the SPA for mobile-first navigation and forms
- create views for:
  - workspace overview
  - recurring meeting series detail
  - meeting occurrence detail
  - organizer content editing
  - participant-facing meeting summary
- add forms for creating recurring schedules
- add UI for editing one occurrence versus the whole series
- add shareable participant-facing meeting summaries with Zoom and location details
- defer teacher dashboard until after the meeting MVP

Suggested route evolution:

- `/dashboard`
- `/w/:workspaceId`
- `/w/:workspaceId/series/:seriesId`
- `/occurrences/:occurrenceId`

Deliverables:

- working mobile web SPA for the MVP wedge
- mobile-usable meeting organizer and participant views

## Phase 5: Notifications and calendar interoperability

Objective:

- make the system useful even when users are not actively in the app

Tasks:

- add notification preferences per user and workspace
- create reminder scheduler job
- add delivery logs and retry handling
- add ICS export or calendar feed
- add email notifications if chosen for MVP

Suggested modules:

- `src/notifications.py`
- `src/delivery_storage.py`
- `src/jobs/send_notifications.py`

Deliverables:

- scheduled reminders
- delivery audit trail
- calendar export

## Phase 6: Meeting organizer assistant

Objective:

- let organizers manage meetings and materials through AI-assisted workflows

Tasks:

- refactor current `committer.py` into a more general assistant service
- support actions such as:
  - create recurring meeting
  - reschedule one occurrence
  - draft meeting material
  - generate shareable reminder text
- require confirmation for state-changing actions
- add streaming assistant responses to the frontend

Suggested modules:

- `src/assistant.py`
- `src/assistant_actions.py`

Deliverables:

- organizer chat assistant
- auditable assistant actions
- structured action execution

## Phase 7: Supervised study and gamification

Objective:

- add teacher oversight and student motivation on top of the core recurrence platform

Tasks:

- build cohort assignment flows
- add teacher dashboard for misses, streaks, and completion summaries
- add badges and streak calculations
- add escalation rules for missed study

Deliverables:

- student check-in loop
- teacher overview
- lightweight gamification

## Phase 8: External messaging assistants

Objective:

- support organizer workflows outside the app

Tasks:

- add Telegram bot first if chat integration is prioritized
- support commands and assistant conversations for organizers
- map bot actions onto the same backend APIs
- evaluate WhatsApp feasibility based on business API constraints
- treat WeChat as a later integration unless there is a clear supported path

Deliverables:

- channel adapter architecture
- first bot integration

---

## 6. Migration Plan from the Current Codebase

### 6.1 Keep during transition

- Firebase Auth setup
- user records
- audit log patterns
- web app shell
- API authentication and middleware

### 6.2 Migrate gradually

- convert `Page` into `Workspace`
- convert `Memory` into either `Occurrence` or legacy imported note, depending on semantics
- move from page-level ownership to workspace roles

### 6.3 Deprecate

- static publisher flow in `src/publisher.py`
- legacy `client/` admin app
- page-centric naming once v2 routes are stable

### 6.4 Compatibility approach

- do not rename everything in one step
- add new v2 modules beside the current ones
- migrate frontend route by route
- remove old concepts only after the new model is stable

---

## 7. Testing Strategy

### 7.1 High-priority unit tests

- recurrence rule expansion
- timezone behavior
- single-occurrence overrides
- notification scheduling windows
- check-in and streak calculations

### 7.2 High-priority integration tests

- workspace role permissions
- organizer creates recurring meeting
- participant receives visible occurrence data
- student check-in updates teacher view
- assistant action preview and confirm flow

### 7.3 Operational tests

- notification retries
- duplicate send protection
- idempotent occurrence generation

---

## 8. Recommended MVP Slice

If speed matters, the best first slice is:

1. mobile web app with Google login
2. workspace
3. recurring meeting series
4. generated meeting occurrences
5. editable single occurrence
6. reminders
7. meeting details: location plus online link
8. organizer-facing content packet
9. organizer-only AI assistant for creating and updating schedules
10. shareable participant summary for copy and paste into other apps

Why this slice:

- it proves the scheduling engine
- it directly serves the strongest differentiated use case
- personal reminders can be added later on the same engine
- it avoids premature complexity from teacher dashboards and external messaging
- it fits the existing Firebase Auth plus React Hosting stack cleanly

Supervised study should come immediately after this slice, not before it.

---

## 9. Key Decisions Needed Before Building

1. Decide the first notification channel after in-app.
2. Decide whether external chat assistant work belongs in MVP or phase 2.
3. Decide whether the brand remains connected to Event Ledger or becomes a new product name.
