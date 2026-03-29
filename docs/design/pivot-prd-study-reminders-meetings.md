# PRD: Pivot to Study, Reminder, and Meeting Assistant

## 1. Product Summary

Pivot Event Ledger from a page-based event board into a product with three connected use cases:

1. Personal reminders for recurring study and daily habits
2. Shared meeting coordination for Christian groups
3. Supervised study with teacher visibility, check-ins, and motivation

The product should work in two operating modes:

- App-first mode: everyone uses the app directly
- Organizer-first mode: only the organizer uses the app and shares outputs into other channels

The product should eventually support both direct in-app experiences and assistant-based workflows through chat channels such as Telegram and WhatsApp.

---

## 2. Vision

Help individuals and small groups stay consistent in study, meetings, and spiritual practice through recurring schedules, reminders, lightweight collaboration, and AI-assisted preparation.

---

## 3. Problem Statement

Current reminder and calendar tools handle one-off events reasonably well, but they are weak at:

- recurring study plans with editable individual occurrences
- small-group meeting preparation and coordination
- mixed-mode participation where not everyone uses the same app
- supervised study where a teacher needs simple visibility into consistency
- lightweight spiritual/community use cases that combine schedule, content, reminders, and follow-up

Users need a system that is simpler than project management software, more collaborative than a basic reminder app, and more structured than chat threads.

---

## 4. Target Users

### 4.1 Personal study user

A single person who wants recurring reminders for study, reading, prayer, or habit-based work.

### 4.2 Meeting organizer

A person coordinating recurring meetings for a Christian group, such as home meetings, young people meetings, prayer meetings, or Bible study gatherings.

### 4.3 Meeting participant

A person who attends meetings and needs reminders, location or Zoom details, and meeting content.

### 4.4 Teacher or teaching assistant

A supervisor who tracks whether students are completing daily study tasks and needs simple progress visibility.

### 4.5 Student

A participant in a supervised study program who checks in daily and receives encouragement, streaks, or badges.

---

## 5. Core Use Cases

### 5.1 Personal recurring reminders

Users can create recurring reminders for study or personal routines.

Requirements:

- schedule types: daily, weekly, weekdays, selected days of week
- configurable time of day
- each occurrence can be modified independently
- user can mark an occurrence done, skipped, or rescheduled
- user can pause or resume a recurring series

Examples:

- daily morning Bible reading at 6:30 AM
- weekday language study at 8:00 PM
- Tuesday and Thursday memorization practice at 7:30 PM

### 5.2 Shared meeting coordination

Organizers manage recurring meetings with participant-facing details and organizer-facing preparation tools.

Requirements:

- recurring meeting schedules
- online meeting link support, especially Zoom
- physical location support
- participant reminders
- calendar export
- organizer workspace for meeting preparation
- shared content for hymns, agenda, notes, reading portions, or announcements
- organizer coordination with co-organizers
- AI assistant for meeting preparation and rescheduling

Two operating modes:

- Full-app mode: organizers and participants all use the app
- Organizer-only mode: organizer uses the app, then copies or pushes content into other apps

Examples:

- Friday home meeting with hymns, topic, Zoom link, and location
- Saturday young people meeting with weekly materials and organizer notes

MVP emphasis:

- the first release should optimize for meeting organizers creating and managing recurring meetings
- organizer-first mode is more important than full participant self-service in the initial release
- only organizers are required to have app accounts in MVP
- personal reminders should reuse the same recurrence engine later
- supervised study should follow after the meeting workflow is stable

### 5.3 Supervised study

Teachers and assistants assign recurring study work and monitor whether students stay consistent.

Requirements:

- recurring study plans for students
- daily or weekly check-in
- teacher or TA visibility into completion status
- streaks, badges, and simple gamification
- lightweight missed-work alerts
- individual and group-level progress views

Examples:

- students complete one reading assignment per day
- teachers review who missed the last three days
- students earn a 14-day streak badge

---

## 6. Product Principles

- recurring-first, not one-off-event-first
- simple enough for personal use
- structured enough for small group coordination
- supports both direct app participation and off-platform sharing
- AI should assist organizers, not replace human control
- mobile notifications and chat-based interaction matter more than desktop complexity

---

## 7. Scope

### 7.1 MVP scope

The first release should focus on the smallest system that proves the pivot:

- mobile web app only
- Google login only
- meeting organizer workflow first
- accounts and workspaces
- recurring schedules
- generated occurrences
- editable occurrence exceptions
- reminders and notification preferences
- meeting details: title, description, location, online link
- organizer and participant roles
- organizer AI assistant for creating and updating schedules or meeting notes
- shareable meeting summaries for copy and paste into other apps

### 7.2 Post-MVP scope

- native mobile apps
- additional login providers
- Telegram assistant
- WhatsApp integration
- WeChat integration if technically and legally feasible
- richer calendar synchronization
- richer teacher dashboards
- content templates by meeting type
- advanced AI planning and suggestion workflows

---

## 8. Functional Requirements

### 8.1 Accounts and spaces

- Users can sign in and manage one or more spaces
- A space can represent a personal workspace, a meeting group, or a supervised study cohort
- A space has roles such as owner, organizer, participant, teacher, assistant, and student

### 8.2 Scheduling model

- Users can create recurring series
- Supported recurrence:
  - daily
  - weekly
  - weekdays
  - selected weekdays
- A series creates concrete occurrences
- A single occurrence can be edited without changing the whole series
- A series can be paused, resumed, or ended
- A missed occurrence can be marked late, skipped, or completed later

### 8.3 Reminders and notifications

- Users can configure when reminders are sent
- Notifications can target organizer only, all participants, or selected subgroups
- Delivery channels should eventually include:
  - in-app push
  - email
  - calendar feed or export
  - Telegram
  - WhatsApp
- Message templates should support meeting reminders and study reminders

### 8.4 Meetings

- Meetings store title, schedule, location, online link, description, and meeting content
- Organizers can attach preparation notes and participant-facing notes separately
- Organizers can coordinate materials before each occurrence
- Organizers can export or copy a formatted meeting summary into other apps

### 8.5 AI assistant

- Organizer can chat with an assistant to:
  - create a recurring meeting
  - reschedule one occurrence
  - update meeting content
  - draft hymns, agenda, or study materials
  - generate a shareable reminder message
- Assistant actions must be previewable before saving for destructive or broad changes
- Participant-facing assistant use is out of scope for the initial version

### 8.6 Supervised study

- Teachers can assign recurring study tasks to a cohort or individual students
- Students can check in completion quickly
- Teachers can see recent completion status, streaks, and misses
- Students can earn badges or streak indicators

### 8.7 Sharing and interoperability

- Every meeting occurrence should have a shareable summary
- Calendar export should be supported early
- Chat channel integrations should be designed behind a notification abstraction rather than hardcoded per feature

---

## 9. Non-Functional Requirements

- mobile-first UX
- responsive mobile web experience as the primary client target
- timezone-aware recurrence and reminders
- auditability for organizer and teacher actions
- reliable reminder delivery with retries
- privacy controls for personal study versus group spaces
- extensible integration architecture for external messaging channels

---

## 10. Proposed Domain Model

### 10.1 Workspace

A container for personal reminders, meeting groups, or supervised study cohorts.

Types:

- personal
- meeting_group
- study_cohort

### 10.2 Series

A recurring plan or template.

Examples:

- daily reading reminder
- Friday home meeting
- weekday student assignment

### 10.3 Occurrence

A single generated instance of a series on a specific date and time.

An occurrence may override the series with exception data such as:

- changed time
- changed location
- changed title
- skipped status
- custom content

### 10.4 Assignment

A series or occurrence assigned to one or more students or participants.

### 10.5 Check-in

A completion or attendance action tied to a user and occurrence.

### 10.6 Content packet

Structured meeting or study content for one occurrence, such as:

- agenda
- hymns
- reading material
- notes
- announcement text
- shareable message text

---

## 11. Success Metrics

### 11.1 MVP metrics

- number of active recurring series per active workspace
- percentage of occurrences that receive a user action
- completion rate for personal reminders
- organizer retention after creating first recurring meeting
- percentage of meetings shared externally from organizer-only mode

### 11.2 Supervised study metrics

- student check-in rate
- streak retention
- teacher weekly return rate

---

## 12. Risks

- The product may be too broad if all three use cases are implemented at once
- External messaging integrations, especially WhatsApp and WeChat, have nontrivial platform constraints
- Recurrence and editable-occurrence logic are easy to get wrong without a clean model
- AI workflows can create trust problems if they modify schedules silently
- Notification delivery will become an operational concern quickly

---

## 13. Product Strategy Recommendation

Do not build all three use cases as separate products. Build one recurring-workspace platform with three packaged entry points:

- Personal Study
- Group Meeting
- Supervised Study

The shared platform should reuse the same primitives:

- workspace
- role
- series
- occurrence
- check-in
- notification
- content packet

This keeps the product coherent and prevents duplicated scheduling logic.

---

## 14. MVP Decision

The MVP wedge is `meeting organizer first`.

Why:

- it is more differentiated than a generic reminder app
- it still forces the product to solve recurrence, occurrence exceptions, reminders, and content preparation
- it supports both future app-first and organizer-only operating modes

Implications:

- recurring meetings are the primary object the MVP information architecture should optimize for
- participant features should be kept lightweight in the first release
- MVP should not depend on participant sign-in or participant account management
- supervised study is explicitly post-MVP

---

## 15. MVP Platform Constraints

These constraints are explicit for the first release:

- client platform: mobile web app
- authentication: Google login only
- primary user experience: browser-based, mobile-first, install-free

Implications:

- no native iOS or Android work in MVP
- no Apple login, email-password login, or phone-number login in MVP
- UI and flows should be optimized for mobile screens first, with desktop as a secondary layout

---

## 16. Open Questions

1. Do participants need attendance tracking in the first release, or only reminders and shared content?
2. Should supervised study be built on the same meeting occurrence model, or as a separate task or assignment model on top of the same recurrence engine?
3. How much of the AI assistant should be free-form chat versus structured actions with confirmation?
4. What is the first notification channel after in-app mobile notifications: email, Telegram, or calendar?
5. Are WhatsApp and WeChat hard requirements, or stretch goals after product-market validation?
6. Should organizers be able to send notifications directly from the app, or only generate copyable messages in MVP?
7. For gamification, what matters most at first: streaks, badges, leaderboards, or teacher recognition views?
8. Does the product need multilingual support from day one, given the likely church-group audience?
9. Does a workspace always map to one group, or can one workspace contain multiple subgroups and meeting series?
10. What privacy boundaries are required between organizer notes, participant-facing content, and teacher-only supervision data?
