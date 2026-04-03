# Manual Test Script

End-to-end use cases for manual testing. Each case lists **preconditions**, numbered
**steps**, and **expected results**. Columns marked **Web** and **App** indicate
which surface to test on. Unless noted otherwise, test both.

---

## 1 Authentication

### 1.1 Sign in with Google

| | Web | App |
|---|---|---|
| Surface | `/` landing | `/sign-in` |

1. Open the app while signed out.
2. Tap **Sign in with Google**.
3. Complete the Google OAuth flow.

**Expected:** User lands on the dashboard. The room list loads (may be empty for a new account).

### 1.2 Sign out

1. From the dashboard, tap the **sign-out** icon / menu.

**Expected:** User returns to the sign-in screen. Navigating to `/dashboard` (web) or `/` (app) redirects back to sign-in.

### 1.3 Auto-redirect when already signed in

1. Sign in.
2. Navigate directly to `/sign-in` (web) or the sign-in route (app).

**Expected:** Automatically redirected to the dashboard.

---

## 2 Rooms

### 2.1 Create a room

1. On the dashboard, tap **+ New** (web) or the **FAB (+)** (app).
2. Enter a room name and select a timezone.
3. Tap **Create**.

**Expected:** The new room appears in the room list. Tapping it opens the room view. The timezone selector defaults to the device/browser's local timezone.

### 2.1a Create a room — timezone auto-detection

1. On a device set to (e.g.) `America/Los_Angeles`, open the create-room form.

**Expected:**
- **Web:** The timezone dropdown defaults to `America/Los_Angeles`.
- **App:** The timezone dropdown defaults to the device's IANA timezone. If the device timezone is not in the hardcoded list, it is added to the dropdown automatically.

### 2.1b Room creation limit

1. Create rooms until you have 10 rooms total.
2. Attempt to create an 11th room.

**Expected:** The API returns a **429** error with the message "Room limit reached. Each user can create up to 10 rooms." The form shows this error message.

### 2.2 Rename a room (organizer only)

1. Open a room you organize.
2. Tap the room title.
3. Change the name and confirm.

**Expected:** Title updates everywhere (room view, dashboard card).

### 2.3 Delete a room (organizer only)

1. Open a room you organize.
2. Tap **Delete room** (in Danger Zone / bottom of screen).
3. Confirm the dialog.

**Expected:** Room is removed. User is redirected to the dashboard. The room no longer appears in the list. If the delete fails (e.g., network error), an alert is shown and the error is logged to the console.

### 2.4 Participant cannot see edit controls

1. Sign in as a **participant** (not organizer).
2. Open a room.

**Expected:** No rename, delete, invite, or create-series controls are visible.

---

## 2a Resources

### 2a.1 Add resources to a room (organizer only)

| | Web | App |
|---|---|---|
| Surface | Room view | Room screen |

1. Open a room you organize.
2. In the **Resources** section, tap **+ Add** (web) or the **Add** button (app).
3. Add a label (e.g., "Meeting Notes") and URL (e.g., `https://docs.google.com/...`).
4. Add a second resource (e.g., label "YouTube Playlist", URL `https://youtube.com/playlist?list=...`).
5. Save.

**Expected:** Both resources appear as clickable links. Tapping a link opens it in a new tab (web) or external browser (app).

### 2a.2 Edit resources on a room (organizer only)

1. Open a room with existing resources.
2. Tap **Edit** on the Resources section.
3. Change a label, change a URL, and remove one resource.
4. Save.

**Expected:** Changes are reflected. The removed resource no longer appears.

### 2a.3 Participant cannot edit resources

1. Sign in as a **participant**.
2. Open a room with resources.

**Expected:** Resources are displayed as clickable links. No Edit or Add button is visible.

### 2a.4 Add resources to a series (organizer only)

1. Open a series (as organizer).
2. In the **Resources** section, tap **+ Add** or **Add**.
3. Add a label and URL. Save.

**Expected:** The resource appears on the series view as a clickable link.

### 2a.5 Add resources to an occurrence (organizer only)

1. Open an occurrence (as organizer).
2. In the **Resources** section, tap **+ Add** or **Add**.
3. Add a label and URL. Save.

**Expected:** The resource appears on the occurrence view as a clickable link.

### 2a.6 Resources are independent per level

1. Add a resource to a room.
2. Open a series in that room — verify the room's resource does not appear on the series.
3. Add a different resource to the series.
4. Open an occurrence — verify neither the room's nor the series' resource appears on the occurrence.

**Expected:** Resources on rooms, series, and occurrences are independent. Each level only shows its own resources.

---

## 3 Membership

### 3.1 Create and share an invite link (organizer only)

1. Open a room you organize.
2. In the Members section, tap **Create Invite Link** (web) or **Invite** (app).
3. Copy the generated link.

**Expected:** A URL is generated and can be copied to the clipboard.

### 3.2 Accept an invite

1. Open the invite link in a browser or the app (while signed out or as a different user).
2. Sign in if prompted.
3. Tap **Accept Invite**.

**Expected:** User is added to the room and navigated to the room view. The new member appears in the member list.

### 3.3 Remove a member (organizer only)

1. Open a room with multiple members.
2. Tap **Remove** next to a participant.
3. Confirm.

**Expected:** The member disappears from the list. They can no longer see the room on their dashboard.

### 3.4 Leave a room (participant)

1. Sign in as a **participant**.
2. Open the room.
3. Tap **Leave** (web) or **Leave room** (app).
4. Confirm.

**Expected:** User is removed and redirected to the dashboard. The room no longer appears.

### 3.5 Sole organizer cannot leave

1. As the only organizer of a room, attempt to leave.

**Expected:** The action is blocked or the leave button is not shown.

---

## 4 Series

### 4.1 Create a series

1. Open a room (as organizer).
2. Tap **+ New Series** (web) or the **FAB (+)** (app).
3. Fill in:
   - Title (required)
   - Frequency: Weekly, select Mon + Wed
   - Time: 19:00
   - Duration: 60
   - Location type: Fixed, enter "Room 101"
   - Online link: any URL
4. Tap **Create**.

**Expected:** Series card appears in the room view with correct schedule summary. Occurrences are generated.

### 4.2 Edit a series (organizer only)

1. Open a series.
2. Tap **Edit**.
3. Change the title, frequency, or duration.
4. Tap **Save**.

**Expected:** Changes are reflected. If frequency/days changed, a confirmation dialog asks whether to adjust or regenerate occurrences.

### 4.3 Edit series schedule — adjust vs regenerate

1. Edit a series and change the day-of-week selection.
2. On the confirmation dialog, choose **Adjust schedule**.

**Expected:** Existing occurrences are kept; new pattern applies going forward.

3. Repeat, but choose **Delete future & regenerate**.

**Expected:** Unmodified future occurrences are deleted and new ones are created matching the new schedule.

### 4.4 Delete a series

1. Open a series (as organizer).
2. Tap **Delete series**.
3. Confirm.

**Expected:** Series and all its occurrences are removed. User is navigated back to the room. If the delete fails, an alert is shown and the error is logged.

### 4.5 Enable "Done" button

1. Edit a series.
2. Toggle **Show "Done" button** on.
3. Optionally restrict to specific weekdays via the day filter.
4. Save.

**Expected:** The "Done" button appears on occurrences that fall on the selected days.

### 4.6 Generate schedule

1. Open a series with no upcoming occurrences.
2. Tap **Generate schedule**.

**Expected:** Occurrences for the next 60 days are created and appear in the list.

### 4.7 Extend schedule to a date

1. Edit a series.
2. Set **Extend schedule to** to a future date.
3. Save.

**Expected:** Occurrences are generated up to the selected date.

### 4.8 Add a single occurrence manually

1. Open a series (as organizer).
2. Tap the **+** (FAB on app, **+ Add occurrence** on web).
3. Pick a date and time.

**Expected:** A new occurrence appears in the timeline at the chosen date/time.

### 4.9 Create a daily series

1. Create a series with frequency **Daily**.

**Expected:** Occurrences are generated for every day. The schedule summary shows "Daily".

### 4.10 Create a weekdays-only series

1. Create a series with frequency **Weekdays**.

**Expected:** Occurrences appear Mon–Fri only. No Saturday/Sunday occurrences.

### 4.11 Create a one-time series (app only)

1. Create a series with frequency **One-time**.

**Expected:** Exactly one occurrence is created.

### 4.12 Series with description (markdown)

1. Create or edit a series and add a multi-line description with markdown (bold, links, bullet lists).
2. Save and view the series.

**Expected:** Description renders as formatted markdown. Links are tappable.

### 4.13 Location modes

**Fixed location:**
1. Create a series with location type **Fixed** and enter an address.
2. View occurrences.

**Expected:** All occurrences show the same fixed location.

**Per-occurrence location:**
1. Create a series with location type **Per occurrence** (web) / **Per Meeting** (app).
2. Edit individual occurrence locations.

**Expected:** Each occurrence can have a different location. Unset occurrences show no location.

**No location:**
1. Create a series with location type **None**.

**Expected:** No location field appears on occurrences (unless manually overridden).

---

## 5 Host Rotation

### 5.1 Configure rotating hosts

1. Edit a series.
2. Set Host Rotation to **Rotating hosts**.
3. Add hosts: Alice, Bob, Carol.
4. Save.

**Expected:** Future occurrences are assigned hosts in the configured order.

### 5.2 Reorder the rotation list

1. Edit a series with rotating hosts.
2. Drag hosts to a new order (app) or use up/down arrows (web).
3. Save.

**Expected:** The rotation order updates.

### 5.3 Configure host + location rotation

1. Edit a series.
2. Set Host Rotation to **Rotate host + location**.
3. Add hosts with addresses.
4. Save.

**Expected:** Each occurrence shows the host's address as its location. Location type controls are hidden (auto-managed by rotation).

### 5.4 Change host on a single occurrence

1. Open an occurrence (as organizer).
2. Edit the host field to a name from the rotation list.
3. Save.

**Expected:** A prompt asks whether to **re-populate the rotation** from this point.

- If **yes**: all subsequent occurrences update their hosts to continue the rotation.
- If **no** (or cancel): only this occurrence changes.

### 5.5 Re-populate rotation from series view

1. In the series view, inline-edit a host on an upcoming occurrence.
2. After saving, a toast / action appears to **Continue rotation from here**.
3. Accept.

**Expected:** Subsequent hosts are updated.

---

## 6 Occurrences

### 6.1 View occurrence detail

1. From the series view, tap any occurrence.

**Expected:** The occurrence detail screen loads with date, time, duration, location, online link, host, and notes.

### 6.2 Navigate between occurrences — prev / next buttons

1. Open any occurrence that has both a previous and next sibling.
2. Tap the **left chevron** (prev) button.
3. Tap the **right chevron** (next) button.
4. Tap **next** again.
5. Tap **prev**.

**Expected:** Each tap loads the correct adjacent occurrence. Navigation works repeatedly (not just once). *(Bug fix: `didUpdateWidget` reload.)*

### 6.3 Navigate between occurrences — swipe (app only)

1. Open an occurrence with siblings.
2. Swipe left (next) and then swipe right (prev).

**Expected:** Same as 6.2 — loads correct adjacent occurrences, works repeatedly.

### 6.4 Navigate between occurrences — keyboard (web only)

1. Open an occurrence (ensure no text input is focused).
2. Press the **right arrow** key, then the **left arrow** key.

**Expected:** Navigates to next/previous occurrence.

### 6.5 Edit occurrence overrides (organizer only)

1. Open an occurrence.
2. Edit the title, location, online link, and notes.
3. Save.

**Expected:** All fields update. Overridden values take precedence over the series defaults.

### 6.6 Toggle "Done" button on a single occurrence

1. Open an occurrence (as organizer).
2. Toggle the **Show "Done" button** switch.

**Expected:** The Done button appears or disappears for that occurrence.

### 6.7 Delete an occurrence (organizer only)

1. Open an occurrence.
2. Tap **Delete occurrence**.
3. Confirm.

**Expected:** Occurrence is deleted. User navigates back. If the delete fails, an alert is shown and the error is logged.

### 6.9 Inline editing in series view (web only)

1. In the series view, click the host / location / notes of an occurrence.
2. Edit inline and submit (Enter / blur / Save button).

**Expected:** Value updates without leaving the page.

---

## 7 Check-In (Done)

### 7.1 Mark as done

1. Open an occurrence with the "Done" button enabled.
2. Tap **Done**.

**Expected:** A green confirmation card appears showing "Done ✓" with an **Undo** button.

### 7.2 Undo a check-in

1. After marking done, tap **Undo**.

**Expected:** The "Done" button reappears. The check-in is removed.

### 7.3 View completions (organizer only)

1. Open an occurrence where participants have checked in.

**Expected:** A "Completions" section lists each user's name, status, and timestamp.

---

## 8 Completion Report

### 8.1 View the completion report

1. Open a series with **Done** enabled and some past occurrences with check-ins.
2. Expand the **Completion Report** section.

**Expected:** A grid shows members vs. past occurrences with check/miss marks. **Only past occurrences appear** (no future dates). *(Bug fix: backend now filters to `scheduled_for < now`.)*

### 8.2 Change the report window size

1. In the completion report, change the "Show last" dropdown to 5, 10, 20, or 50.

**Expected:** The grid updates to show the last N past occurrences. The count is backward from the most recent past occurrence.

### 8.3 Report with no data

1. Open a series with Done enabled but no past occurrences.

**Expected:** Displays "No practice data" or an empty state — no crash.

---

## 9 Occurrence Summary (Shareable Page)

### 9.1 Open the share panel

1. Open an occurrence with a location or online link.
2. Tap **Share**.

**Expected:** A share panel expands showing the summary URL, a **Copy** button, and a **Preview** link. For organizers, an **Include invite link** checkbox is also shown.

### 9.2 Copy the share link

1. In the share panel, tap **Copy**.

**Expected:** The URL is copied to the clipboard. The button text briefly changes to "Copied!"

### 9.2a Include invite link (organizer only)

1. As an organizer, open the share panel.
2. Check **Include invite link (joins as participant)**.

**Expected:** The displayed URL updates to include `?invite={inviteId}`. The invite is created with the **participant** role. Unchecking removes the invite param.

### 9.2b Include invite — non-organizer cannot see toggle

1. As a participant or teacher, open the share panel.

**Expected:** The **Include invite link** checkbox is not visible.

### 9.3 Join online meeting from summary

1. On the summary page, tap **Join online meeting**.

**Expected:** The meeting URL opens in a new tab / external browser.

### 9.4 View summary while signed out (Web only)

1. Sign out (or open an incognito / private window).
2. Navigate directly to an occurrence summary URL (`/occurrences/{id}/summary`).

**Expected:** The page loads without requiring sign-in. All read-only fields (title, date, duration, location, link, notes) display correctly. (The app still requires sign-in for the summary screen.)

### 9.5 Summary with invite link — join button and QR code (Web only)

1. As an organizer, open the share panel and check **Include invite link**.
2. Tap **Preview** or open the copied URL in an incognito window.

**Expected:** The summary page shows a **Join this group** button and a QR code. Tapping the button navigates to the invite acceptance flow. The QR code encodes the invite URL.

### 9.6 Summary without invite link — no join controls (Web only)

1. Open the summary URL without an `?invite=` query param.

**Expected:** No "Join this group" button or QR code is shown. The page displays only the read-only meeting summary.

---

## 10 Telegram Bot Integration (Web + App, Organizer Only)

### 10.1 Connect a Telegram bot

1. Open a room (as organizer).
2. In the Telegram / AI Assistant section, enter a valid bot token.
3. Select a mode (Read-only or Read & Write).
4. Tap **Connect Bot**.

**Expected:** The bot info card appears showing the bot username and active status.

### 10.2 Switch bot mode

1. With a bot connected, toggle between **Read-only** and **Read & Write**.

**Expected:** The mode updates immediately.

### 10.3 Generate a link code and link a Telegram account

1. In the app, tap **Generate Link Code**.
2. Copy the 6-character code.
3. Open the bot in Telegram and send `/link <code>`.

**Expected:**
- The code appears in the app with a countdown timer (5 min expiry).
- The bot responds in Telegram: "You're verified as [Name]. You can now manage [Room Title]."

### 10.4 Unlinked user messages the bot

1. Message the bot from a Telegram account that has **not** been linked.

**Expected:** The bot replies with instructions to generate a link code and send `/link <code>`.

### 10.5 Chat with the bot in read-only mode

1. Set the bot to **Read-only** mode.
2. Message the bot: "When is the next meeting?"

**Expected:** The bot answers with schedule information. It does **not** offer to create or modify anything.

### 10.6 Chat with the bot in read-write mode

1. Set the bot to **Read & Write** mode.
2. Message the bot: "Reschedule tomorrow's meeting to 3pm."

**Expected:** The bot proposes an action with **Confirm** / **Cancel** inline buttons.

### 10.7 Confirm a bot action via inline button

1. After the bot proposes an action (10.6), tap **Confirm** in Telegram.

**Expected:** The action executes. The bot edits the message to confirm the change.

### 10.8 Cancel a bot action via inline button

1. After the bot proposes an action, tap **Cancel** in Telegram.

**Expected:** The action is discarded. The bot edits the message to show cancellation.

### 10.9 Bot conversation memory

1. Send the bot a message: "Change the next meeting location to Room 202."
2. Confirm the action.
3. Send a follow-up: "Actually, make that Room 303 instead."

**Expected:** The bot understands "that" refers to the same meeting and proposes updating the location.

### 10.10 Bot in group chat (unsupported)

1. Add the bot to a Telegram group chat.
2. Send a message.

**Expected:** The bot replies that it only supports private chats.

### 10.11 Disconnect a bot

1. Tap **Disconnect bot** in the app.
2. Confirm.

**Expected:** The bot is removed. The connect form reappears. Messaging the bot in Telegram no longer works.

---

## 11 Notification Rules

### 11.1 Create a notification rule (API)

1. `POST /v2/rooms/{room_id}/notification-rules` with a rule body (e.g., remind 1 hour before).

**Expected:** Rule is saved. `GET /v2/rooms/{room_id}/notification-rules` returns it.

### 11.2 Delete a notification rule (API)

1. `DELETE /v2/notification-rules/{rule_id}`.

**Expected:** Rule is removed. No longer returned in the list.

### 11.3 Notification delivery

1. Create a notification rule for a room with upcoming occurrences.
2. Wait for the scheduled delivery time.

**Expected:** Notification is delivered through the configured channel. Delivery log is recorded.

---

## 12 AI Assistant — In-App (Web, Organizer Only)

### 12.1 Send a message to the assistant

1. Open the assistant chat for a room (web).
2. Type a message (e.g., "Schedule a meeting next Tuesday at 3pm").
3. Submit.

**Expected:** The assistant responds with a proposed action and Confirm/Cancel buttons.

### 12.2 Confirm an assistant action

1. After the assistant proposes an action, tap **Confirm**.

**Expected:** The action executes (e.g., occurrence created). Confirmation message appears.

### 12.3 Cancel an assistant action

1. After the assistant proposes an action, tap **Cancel**.

**Expected:** The action is discarded. No changes are made.

### 12.4 Read-only queries via assistant

1. Ask the assistant: "What's on the schedule this week?"

**Expected:** The assistant responds with relevant schedule info without proposing changes.

### 12.5 Create a single occurrence via assistant

1. Open the assistant chat for a room with an existing series (web or Telegram bot in read-write mode).
2. Send: "Create an occurrence of the series on 4/5, the agenda is Unit 4 Lesson 9, hosts are Zhi Han and Augustine Ho."
3. Review the proposed action.
4. Tap **Confirm**.

**Expected:** The assistant proposes a `create_occurrence` action with the correct series, date, agenda/notes, and hosts. After confirmation, a new occurrence appears in the series at the specified date with the provided agenda and hosts.

### 12.6 Update hosts on multiple occurrences via assistant

1. Open the assistant chat for a room with a series that has at least 3 upcoming occurrences (web or Telegram bot in read-write mode).
2. Send: "Update the hosts for the next three meetings: Augustine Ho and Sharon Ho; Sharon Ho and Indigo Kuo; Indigo Kuo and Sybil Li."
3. Review the proposed action(s).
4. Tap **Confirm**.

**Expected:** The assistant proposes an `update_occurrence` action (batch of 3) mapping each host pair to the correct occurrence. After confirmation, the three occurrences show their updated hosts.

### 12.7 Add resource links via assistant

1. Open the assistant chat for a room (web or Telegram bot in read-write mode).
2. Send: "Add a resource link to the room: label 'Meeting Notes', URL https://docs.google.com/example."
3. Review the proposed action.
4. Tap **Confirm**.

**Expected:** The assistant proposes an `update_room` action with the correct links payload. After confirmation, the resource link appears in the room's Resources section.

### 12.8 Update series fields via assistant

1. Open the assistant chat for a room with an existing series.
2. Send: "Change the meeting location for [series name] to Room 303."
3. Review the proposed action.
4. Tap **Confirm**.

**Expected:** The assistant proposes an `update_series` action with the correct `default_location`. After confirmation, the series shows the updated location.

---

## 13 Cross-Cutting Concerns

### 13.1 Pull-to-refresh (app only)

1. On any data screen (dashboard, room, series, occurrence), pull down to refresh.

**Expected:** Data reloads. Any changes made elsewhere are reflected.

### 13.2 Error states and retry

1. Disconnect from the network.
2. Navigate to any screen.

**Expected:** An error message appears with a **Retry** button. Reconnecting and tapping Retry loads the data.

### 13.3 Role-based access control — participant

1. Sign in as a **participant**.
2. Visit a room, series, and occurrence.

**Expected:** No edit, delete, invite, or management controls are visible. Only "Done", "Leave", and read-only content is accessible.

### 13.4 Deep links / direct URL navigation (web)

1. Copy the URL of an occurrence and open it in a new tab.
2. Copy an invite link and open it in a new incognito window.

**Expected:** The correct screen loads (with sign-in redirect if needed).

### 13.5 Deep links / invite links (app)

1. Open an invite link (`https://small-group.ai/invites/{id}`) on a device with the app installed.

**Expected:** The app opens to the accept-invite screen. If not signed in, the user signs in first, then accepts.

### 13.6 Session restore on app launch (app only)

1. Sign in to the app.
2. Force-close and reopen the app.

**Expected:** The user is automatically signed in and lands on the dashboard without needing to sign in again.

### 13.7 Markdown rendering

1. Add markdown content to a series description or occurrence notes (e.g., `**bold**`, `[link](https://example.com)`, bullet lists).
2. View the series or occurrence.

**Expected:** Markdown renders correctly. Links are tappable and open externally.

### 13.8 Timezone display — same timezone (hidden)

1. Create a room with timezone matching your current device/browser timezone (e.g., if you are in `America/New_York`, set the room to `America/New_York`).
2. View the room, series, and occurrence screens.

**Expected:** No timezone indicator is shown anywhere. The room view does **not** display the timezone label beneath the title. Dates show a single formatted time (e.g., "Fri, Jan 3, 7:00 PM") with no timezone abbreviation.

### 13.9 Timezone display — different timezone (dual format)

1. Create a room with timezone set to a **different** timezone from your device (e.g., create a room in `Asia/Tokyo` while your device is in `America/New_York`).
2. View the series view and occurrence detail.

**Expected:**
- **Web — Room view:** The room timezone is shown beneath the title (e.g., "Asia/Tokyo").
- **Web — Series & occurrence dates:** Dates display in dual format: `"Fri, Jan 3, 7:00 PM (JST) / Fri, Jan 3, 5:00 AM (EST)"` showing room timezone first, then the user's local timezone.
- **App — Room view:** The timezone globe icon and label are shown.
- **App — Series & occurrence dates:** Dates include the timezone abbreviation (e.g., "Jan 3, 2025  19:00 (JST)") and a secondary line shows "Room: Tokyo".

### 13.10 Timezone — equivalent IANA zones

1. Create a room with timezone `Asia/Taipei`.
2. Set your device timezone to `Asia/Shanghai` (both are UTC+8 year-round).
3. View the room.

**Expected:** Timezone is treated as matching — no dual display, no timezone label shown. The comparison normalizes IANA zone names rather than comparing strings directly.

### 13.11 Long input validation

1. Try creating a room/series with an empty title.

**Expected:** Validation prevents submission (title is required).

### 13.12 Concurrent editing

1. Open the same series in two browser tabs (as organizer).
2. Edit the host on one occurrence in tab A, then edit the same occurrence in tab B.

**Expected:** The second save succeeds (last-write-wins). Refreshing either tab shows the final state.

### 13.13 Error logging

1. Open the browser console (web) or debug log (app).
2. Disconnect from the network.
3. Attempt an action that triggers an API call (e.g., create a room, mark done, delete an occurrence).

**Expected:** The error is shown to the user (alert or error banner) **and** logged to the console:
- **Web:** `console.error(...)` appears with the error details and the operation context (e.g., "Failed to create room: ...").
- **App:** `debugPrint(...)` output appears in the debug log with `ERROR:` or `WARN:` prefix.
- **Backend:** Python `logger.warning(...)` or `logger.error(...)` entries appear in server logs.

No errors are silently swallowed — every catch block produces a log entry.
