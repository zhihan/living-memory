# Migration Strategy: Pages/Memories to Workspaces/Series/Occurrences

## Overview

The pivot introduces new top-level domain objects that replace the old Page and
Memory models. Old collections remain read-only during the transition; no existing
data is deleted until a migration script is explicitly run and verified.

## Mapping: old to new

| Old concept        | New concept                          | Notes                                   |
|--------------------|--------------------------------------|-----------------------------------------|
| Page               | Workspace                            | slug becomes workspace_id (or new UUID) |
| Page.owner_uids    | Workspace.owner_uids + member_roles  | owners get role "organizer"             |
| Page.member_uids   | member_roles[uid]="participant"      | explicit role                           |
| Page.visibility    | Workspace.type                       | "public" -> "shared", "personal" stays  |
| Page.timezone      | Workspace.timezone                   | direct copy, default "UTC"              |
| Memory             | Occurrence (no Series parent)        | one-time, standalone occurrence         |
| Memory.target      | Occurrence.scheduled_for             | date -> UTC datetime at midnight        |
| Memory.title       | Occurrence.overrides.title           | stored in overrides                     |
| Memory.place       | Occurrence.overrides.location        | direct copy                             |
| Memory.time        | Occurrence.overrides.time            | direct copy                             |

## New collections (this phase)

- workspaces
- series
- occurrences
- check_ins
- notification_rules
- delivery_logs

## Preserved collections (unchanged)

- pages
- memories
- users
- audit_log

## Migration Steps (manual, when ready)

1. Backfill workspaces: for each doc in `pages`, call workspace_storage.create_workspace().
2. Backfill occurrences: for each doc in `memories`, create a standalone Occurrence.
3. Validate counts and spot-check a sample on both sides.
4. Dual-read window: API v1 routes read from both old and new collections.
5. Deprecate: archive old collections once API v2 is stable.

## Backward Compatibility

- src/page_storage.py and src/firestore_storage.py are unchanged.
- All v1 API endpoints continue to work.
- New modules (models.py, workspace_storage.py, series_storage.py) are additive only.
- The React web app continues to use the v1 API until Phase 4.
