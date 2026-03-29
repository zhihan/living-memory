# Executive Summary: Study, Reminder, and Meeting Assistant

## What We're Building

A recurring-schedule platform that serves three connected use cases: personal study reminders, shared meeting coordination for Christian groups, and supervised study with teacher oversight. One unified engine powers all three — workspaces, recurring series, editable occurrences, check-ins, and notifications.

## Problem

Existing tools handle one-off events well but are weak at recurring study plans with per-instance editing, small-group meeting preparation, mixed-mode participation (not everyone uses the same app), and lightweight supervised study. Users need something simpler than project management software, more collaborative than a reminder app, and more structured than group chat.

## MVP: Meeting Organizer First

The first release focuses exclusively on meeting organizers managing recurring meetings. This is the most differentiated use case and solves the hardest technical problem — recurrence with editable single instances — which every subsequent feature depends on.

MVP delivers: mobile web app with Google login, workspaces, recurring meeting series, generated occurrences with per-instance editing, meeting details (location, Zoom link, content), and shareable meeting summaries for copy-paste into other channels.

The product includes an always-on AI assistant with a chat interface that helps meeting organizers create and update schedules, draft meeting content, reschedule occurrences, and generate shareable reminder messages. Telegram and WhatsApp will be the first supported messaging channels, starting with whichever is easier to implement.

MVP explicitly excludes: native mobile apps, supervised study, and participant account requirements.

## Two Operating Modes

- **App-first**: organizers and participants all use the app directly.
- **Organizer-only**: the organizer uses the app and shares outputs into Telegram, WhatsApp, or other channels. Only organizers need accounts in the initial release.

## Platform

- Mobile web only (no native apps in MVP)
- Google sign-in only
- Firebase Auth, FastAPI, Firestore, and React

## Roadmap After MVP

1. Personal recurring reminders (same recurrence engine, lighter UI)
2. Supervised study with teacher dashboards, student check-ins, streaks, and badges
3. External messaging integrations (Telegram first, then WhatsApp)
4. Native mobile apps and additional login providers

## Key Risks

- Recurrence with timezone-aware occurrence generation and single-instance exceptions is technically complex
- Scope across three use cases can dilute focus if not phased strictly
- Notification delivery becomes an operational concern quickly
- External messaging integrations (WhatsApp, WeChat) have significant platform constraints

## Decisions Needed

1. First notification channel after in-app (email or calendar feed)
2. First messaging channel for the AI assistant (Telegram or WhatsApp, based on implementation complexity)
3. Product name
