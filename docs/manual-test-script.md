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

**Expected:** The new room appears in the room list. Tapping it opens the room view.

### 2.2 Rename a room (organizer only)

1. Open a room you organize.
2. Tap the room title.
3. Change the name and confirm.

**Expected:** Title updates everywhere (room view, dashboard card).

### 2.3 Delete a room (organizer only)

1. Open a room you organize.
2. Tap **Delete room** (in Danger Zone / bottom of screen).
3. Confirm the dialog.

**Expected:** Room is removed. User is redirected to the dashboard. The room no longer appears in the list.

### 2.4 Participant cannot see edit controls

1. Sign in as a **participant** (not organizer).
2. Open a room.

**Expected:** No rename, delete, invite, or create-series controls are visible.

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

**Expected:** Series and all its occurrences are removed. User is navigated back to the room.

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

**Expected:** Occurrence is deleted. User navigates back.

### 6.8 Inline editing in series view (web only)

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

### 9.1 View the shareable summary

1. Open an occurrence with a location or online link.
2. Tap **View shareable page**.

**Expected:** A clean read-only page displays the meeting title, date/time, duration, location, online link, and notes.

### 9.2 Copy the summary link

1. On the summary page, tap **Copy link**.

**Expected:** The URL is copied to the clipboard. The button text briefly changes to "Copied!"

### 9.3 Join online meeting from summary

1. On the summary page, tap **Join online meeting**.

**Expected:** The meeting URL opens in a new tab / external browser.

---

## 10 Telegram Bot Integration (Web + App, Organizer Only)

### 10.1 Connect a Telegram bot

1. Open a room.
2. In the Telegram section, enter a valid bot token.
3. Select a mode (Read-only or Read & Write).
4. Tap **Connect Bot**.

**Expected:** The bot info card appears showing the bot username and active status.

### 10.2 Switch bot mode

1. With a bot connected, toggle between **Read-only** and **Read & Write**.

**Expected:** The mode updates immediately.

### 10.3 Generate a link code

1. Tap **Generate Link Code**.

**Expected:** A one-time code appears with a countdown timer. The code can be copied.

### 10.4 Disconnect a bot

1. Tap **Disconnect bot**.
2. Confirm.

**Expected:** The bot is removed. The connect form reappears.

---

## 11 Notifications (Web only)

### 11.1 Create a notification rule

*Verify via the API or any UI surface that exposes notification rules.*

1. Create a notification rule for a room (e.g., "Remind 1 hour before each occurrence").

**Expected:** The rule is saved and notifications are delivered at the configured time.

---

## 12 ICS Export (Web)

### 12.1 Download occurrence ICS

1. Navigate to an occurrence and trigger ICS download (via direct URL or UI button if available).

**Expected:** A valid `.ics` file downloads that can be opened in a calendar app.

### 12.2 Download series ICS

1. Navigate to a series and trigger ICS download.

**Expected:** A valid `.ics` file downloads containing all occurrences in the series.

---

## 13 AI Assistant (Organizer Only)

### 13.1 Send a message to the assistant

1. Open the assistant chat for a room.
2. Type a message (e.g., "Schedule a meeting next Tuesday at 3pm").
3. Submit.

**Expected:** The assistant responds with a proposed action.

### 13.2 Confirm an assistant action

1. After the assistant proposes an action, tap **Confirm**.

**Expected:** The action executes (e.g., occurrence created). Confirmation message appears.

### 13.3 Cancel an assistant action

1. After the assistant proposes an action, tap **Cancel**.

**Expected:** The action is discarded. No changes are made.

---

## 14 Cross-Cutting Concerns

### 14.1 Pull-to-refresh (app only)

1. On any data screen (dashboard, room, series, occurrence), pull down to refresh.

**Expected:** Data reloads. Any changes made elsewhere are reflected.

### 14.2 Error states and retry

1. Disconnect from the network.
2. Navigate to any screen.

**Expected:** An error message appears with a **Retry** button. Reconnecting and tapping Retry loads the data.

### 14.3 Role-based access control

1. Sign in as a **participant**.
2. Visit a room, series, and occurrence.

**Expected:** No edit, delete, invite, or management controls are visible. Only "Done", "Leave", and read-only content is accessible.

### 14.4 Deep links / direct URL navigation

1. Copy the URL of an occurrence (web) and open it in a new tab.
2. Copy an invite link and open it in a fresh browser / app instance.

**Expected:** The correct screen loads (with sign-in if needed).

### 14.5 Markdown rendering

1. Add markdown content to a series description or occurrence notes (e.g., `**bold**`, `[link](https://example.com)`, bullet lists).
2. View the series or occurrence.

**Expected:** Markdown renders correctly. Links are tappable and open externally.
