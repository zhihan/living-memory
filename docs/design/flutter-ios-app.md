# Flutter Mobile App — Plan

## Goal

Build a Flutter mobile app for iOS and Android that reuses the existing FastAPI backend.
The app should cover the core scheduling flows from the web app, optimized for mobile.

## Why Flutter

- One codebase for iOS and Android
- Existing backend and Firebase auth model can be reused directly
- Mobile-specific UI can diverge from the web app without duplicating backend logic

## Authentication

- Use Google Sign-In in Flutter
- Exchange the Google credential for a Firebase ID token via `firebase_auth`
- Attach the Firebase ID token on every API request as `Authorization: Bearer <token>`
- Reuse the existing backend token verification with no auth-specific backend changes
- Firebase project: `living-memories-488001`

## API Layer

The mobile app should call the existing `/v2/...` API surface using a configurable base host.

Examples:

- Production host: `https://living-memories-488001.web.app`
- Request path: `/v2/workspaces`, `/v2/series/{id}`, `/v2/occurrences/{id}`, etc.

Existing endpoints already cover the main mobile flows:

| Area | Endpoints |
|------|-----------|
| Workspaces | `POST/GET/PATCH/DELETE /v2/workspaces/...` |
| Members & Invites | `GET/POST/DELETE /v2/workspaces/{id}/members`, `POST /v2/workspaces/{id}/invites`, `POST /v2/invites/{id}/accept` |
| Series | `POST/GET/PATCH/DELETE /v2/series/...`, `GET /v2/series/{id}/check-in-report` |
| Occurrences | `GET /v2/workspaces/{id}/occurrences`, `GET /v2/series/{id}/occurrences`, `POST /v2/series/{id}/occurrences/generate`, `GET/PATCH /v2/occurrences/{id}` |
| Check-ins | `POST/GET /v2/occurrences/{id}/check-ins`, `GET /v2/occurrences/{id}/my-check-in`, `PATCH/DELETE /v2/check-ins/{id}` |
| Notifications | `GET/POST /v2/workspaces/{id}/notification-rules`, `DELETE /v2/notification-rules/{id}` |

## Scope

**In scope (v1):**

- Google Sign-In with Firebase Auth
- Workspace dashboard
- Workspace detail and member/invite management
- Series create/edit flows
- Occurrence detail and organizer edits
- Participant self check-in
- Organizer/teacher check-in report
- Pull-to-refresh on list screens
- iOS and Android builds from the same Flutter app

**Not in scope (v1):**

- Assistant / chat flows
- Telegram webhook management
- Push notifications
- Offline mode / local persistence
- ICS export UI beyond opening a browser link if needed

## Product Notes

- Mobile v1 should target the core scheduling flows, not full web parity
- Role-aware behavior matters:
  - `organizer`: full workspace management
  - `teacher`: series/occurrence management and check-in reporting
  - `participant`: self-service viewing and check-in
- Series location modes already exist in the backend and web app:
  - `fixed`
  - `per_occurrence`
  - `rotation`

## Screens

### 1. Sign-In

- Google Sign-In button
- Restore existing session on app launch
- Navigate to Dashboard on success

### 2. Dashboard

- List of user workspaces from `GET /v2/workspaces`
- Create workspace action
- Tap workspace to open Workspace View

### 3. Workspace View

- Workspace title and timezone
- Organizer-only workspace title editing
- List of series with schedule summary
- New Series form
- Members list with role badges
- Organizer-only invite generation
- Tap series to open Series View

### 4. Series View

- Series details: title, description, schedule, location mode, default link
- Organizer/teacher edit form
- Next meeting card
- Last meeting card
- Upcoming occurrences list
- Inline location editing for per-occurrence flows
- Generate more occurrences action
- Check-in report table with window selector

### 5. Occurrence View

- Date, title, location, online link, notes
- Organizer/teacher status controls
- Organizer/teacher check-in toggle
- Organizer/teacher edit occurrence overrides
- Participant self check-in and undo
- Organizer/teacher full check-in list
- Participant own check-in state

### 6. Accept Invite

- Handle `/invites/{id}` deep links
- Prompt signed-in user to accept
- Call `POST /v2/invites/{id}/accept`
- Navigate to the workspace on success

Note:

- The current API supports invite acceptance directly
- If the app should display workspace title or invite role before acceptance, add a small invite-preview endpoint later

## Project Structure

```text
flutter_app/
├── lib/
│   ├── main.dart
│   ├── app/
│   │   ├── router.dart
│   │   ├── theme.dart
│   │   └── config.dart
│   ├── services/
│   │   ├── auth_service.dart
│   │   ├── api_service.dart
│   │   └── session_service.dart
│   ├── models/
│   │   ├── workspace.dart
│   │   ├── series.dart
│   │   ├── occurrence.dart
│   │   ├── check_in.dart
│   │   └── notification_rule.dart
│   ├── features/
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── workspace/
│   │   ├── series/
│   │   ├── occurrence/
│   │   └── invites/
│   └── shared/
│       ├── widgets/
│       ├── formatting/
│       └── errors/
├── ios/
├── android/
├── pubspec.yaml
└── firebase_options.dart
```

## Key Dependencies

```yaml
dependencies:
  flutter:
    sdk: flutter
  firebase_core: ^3.x
  firebase_auth: ^5.x
  google_sign_in: ^6.x
  http: ^1.x
  provider: ^6.x
  intl: ^0.19.x
  url_launcher: ^6.x
```

## Deep Links

Support invite links on both platforms:

- iOS: Universal Links
- Android: App Links
- Existing web invite URL shape: `https://living-memories-488001.web.app/invites/{id}`

Optional:

- Add a custom scheme such as `eventledger://invites/{id}` for debugging or non-web entry points

## Delivery Plan

### Phase 1

- Flutter app scaffold
- Firebase setup
- Google Sign-In
- Shared API client with token attachment and 401 retry
- Dashboard and workspace list

### Phase 2

- Workspace detail
- Series create/edit
- Member list and invite generation
- Invite acceptance

### Phase 3

- Series occurrences
- Occurrence editing
- Self check-in
- Organizer/teacher check-in report

### Phase 4

- UX polish for mobile navigation, loading, and error states
- iOS and Android release hardening

## Migration Path

The Flutter app and web app coexist against the same backend and Firebase project.
No data migration is required.

## Implementation Task List

Use this section as the execution plan for an implementation agent.

### 1. Scaffold the Flutter app

- Create `flutter_app/` with iOS and Android enabled
- Generate Firebase config with FlutterFire for `living-memories-488001`
- Add baseline dependencies in `pubspec.yaml`
- Create initial app structure:
  - `lib/main.dart`
  - `lib/app/router.dart`
  - `lib/app/theme.dart`
  - `lib/app/config.dart`
  - `lib/services/`
  - `lib/models/`
  - `lib/features/`
  - `lib/shared/`

Done when:

- `flutter run` works on iOS simulator
- `flutter run` works on Android emulator
- App launches to a placeholder shell screen without runtime errors

### 2. Implement auth and session bootstrap

- Add Google Sign-In flow using `google_sign_in` and `firebase_auth`
- Restore prior session on app launch
- Expose current auth state to the app
- Implement sign-out
- Add token retrieval helper for authenticated API requests

Primary files:

- `lib/services/auth_service.dart`
- `lib/services/session_service.dart`
- `lib/features/auth/`

Done when:

- User can sign in on iOS
- User can sign in on Android
- App restores session after restart
- App can sign out cleanly

### 3. Build the shared API client

- Implement configurable API host handling
- Send `Authorization: Bearer <token>` on every request
- Retry once on `401` with a fresh Firebase token
- Normalize backend errors into a consistent app error type
- Add typed methods for:
  - workspaces
  - members
  - invites
  - series
  - occurrences
  - check-ins
  - notification rules

Primary files:

- `lib/services/api_service.dart`
- `lib/models/*.dart`
- `lib/shared/errors/`

Done when:

- The client can hit at least one authenticated endpoint successfully
- Token refresh on `401` works
- Common error messages are surfaced predictably

### 4. Define API models

- Port the response/request shapes used by the mobile app from the existing web API
- Include models for:
  - `Workspace`
  - `Series`
  - `Occurrence`
  - `CheckIn`
  - `NotificationRule`
- Include schedule and occurrence override sub-models
- Include role-aware fields such as `member_roles`

Done when:

- All API client methods return typed models
- JSON serialization and deserialization are covered for the core models

### 5. Implement app routing and guarded navigation

- Add routes for:
  - sign-in
  - dashboard
  - workspace
  - series
  - occurrence
  - accept invite
- Redirect unauthenticated users to sign-in
- Route authenticated users away from sign-in to dashboard
- Support navigation from notifications or deep links into the correct screen later

Primary files:

- `lib/app/router.dart`
- `lib/main.dart`

Done when:

- Route guards work for signed-in and signed-out states
- App can navigate end-to-end between all implemented screens

### 6. Build the Sign-In screen

- Add Google Sign-In CTA
- Show loading and auth error states
- Auto-forward signed-in users to dashboard

Primary files:

- `lib/features/auth/sign_in_screen.dart`

Done when:

- A signed-out user can reach dashboard through the UI

### 7. Build the Dashboard screen

- Fetch and render workspaces from `GET /v2/workspaces`
- Add create-workspace flow
- Add pull-to-refresh
- Navigate into a workspace on tap

Primary files:

- `lib/features/dashboard/`

Done when:

- User can view workspaces
- User can create a workspace
- Refresh and empty states are handled

### 8. Build the Workspace screen

- Fetch workspace detail, series list, and members
- Show workspace title and timezone
- Support organizer-only title editing
- Render members with role badges
- Support organizer-only invite generation
- Support organizer-only member management if included in v1
- Add new-series form with:
  - title
  - description
  - frequency
  - weekdays
  - time
  - duration
  - location
  - online link
  - location type
  - check-in days

Primary files:

- `lib/features/workspace/`

Done when:

- Organizer can create a series
- Organizer can generate an invite link
- Workspace loads with members and series

### 9. Build the Series screen

- Fetch series and occurrences
- Render schedule summary and metadata
- Support organizer/teacher editing
- Support location modes:
  - `fixed`
  - `per_occurrence`
  - `rotation`
- Show next and last meeting cards
- Render upcoming occurrences list
- Allow generate-more-occurrences action
- Build organizer/teacher check-in report table
- Add report window selector

Primary files:

- `lib/features/series/`
- `lib/shared/widgets/check_in_report.dart`

Done when:

- Organizer or teacher can edit a series
- Organizer or teacher can generate occurrences
- Check-in report loads and renders correctly

### 10. Build the Occurrence screen

- Fetch occurrence details
- Fetch series/workspace context if needed for rendering
- Render effective title, location, link, duration, and notes
- Support organizer/teacher updates:
  - status
  - enable check-in
  - overrides
  - location edits
- Support participant self check-in
- Support self undo by deleting or updating the user check-in
- Show full check-in list for organizer/teacher
- Show current user check-in state for participant

Primary files:

- `lib/features/occurrence/`

Done when:

- Organizer/teacher can edit occurrence state
- Participant can check in and undo
- Role-based UI is enforced correctly

### 11. Implement invite deep-link handling

- Support incoming invite links on iOS and Android
- Route `/invites/{id}` into the accept-invite screen
- Require sign-in before acceptance if needed
- Call `POST /v2/invites/{id}/accept`
- Navigate to the workspace on success

Primary files:

- `lib/features/invites/`
- platform link configuration under `ios/` and `android/`

Done when:

- Opening an invite link on a signed-out device leads through sign-in and then acceptance
- Opening an invite link on a signed-in device lands in the workspace after acceptance

### 12. Add notification rule support if kept in v1 UI

- Decide whether notification rules are user-visible in mobile v1
- If yes, implement list/create/delete flows for organizer
- If no, leave API client support in place but skip screen work

Done when:

- Scope decision is explicit in code and doc

### 13. Harden UX states

- Add loading, empty, retry, and error states on every screen
- Add pull-to-refresh where list data is shown
- Add confirmation UX for destructive actions
- Make role-restricted actions visually obvious
- Check small-screen layout behavior on both platforms

Done when:

- No major screen blocks on unhandled loading or error states
- Core flows are usable on typical phone sizes

### 14. Verify parity against the backend

- Test each implemented API method against the current backend
- Verify organizer, teacher, and participant permissions
- Verify check-in report visibility rules
- Verify invite creation and acceptance
- Verify location mode behavior

Done when:

- No mobile flow depends on a missing backend endpoint
- Any API gaps are documented explicitly

### 15. Release hardening

- Configure app icons, bundle IDs, package names, and signing setup
- Validate release builds for iOS and Android
- Confirm production API host configuration
- Confirm deep-link domain setup for both platforms

Done when:

- Release builds can be produced for both platforms
- Production auth and API configuration are documented

## Suggested Execution Order

1. Scaffold app, Firebase, and auth
2. Build API client and typed models
3. Add routing and sign-in screen
4. Implement dashboard and workspace flows
5. Implement series and occurrence flows
6. Implement invite deep links
7. Harden UX and verify role-based behavior
8. Finish release configuration

## Explicit Non-Goals For The Implementing Agent

- Do not add new backend endpoints unless blocked by a concrete UI requirement
- Do not implement assistant/chat flows in mobile v1
- Do not implement push notifications in mobile v1
- Do not implement offline sync in mobile v1

## Known API Gap

- The current backend supports invite acceptance but not invite preview metadata
- If product requires showing workspace name or role before acceptance, add a small read endpoint such as `GET /v2/invites/{invite_id}`
