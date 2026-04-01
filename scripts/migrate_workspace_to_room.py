#!/usr/bin/env python3
"""One-time migration: rename workspace_id → room_id in all Firestore documents.

Usage:
    python scripts/migrate_workspace_to_room.py [--dry-run]

Migrates these collections:
    workspaces        — workspace_id → room_id
    series            — workspace_id → room_id
    occurrences       — workspace_id → room_id
    check_ins         — workspace_id → room_id
    notification_rules — workspace_id → room_id
    delivery_logs     — workspace_id → room_id

Each document that has a "workspace_id" field gets a "room_id" field added
with the same value, and "workspace_id" is removed.

Safe to run multiple times — skips documents that already have "room_id".
"""

import argparse
import os
import sys

# Allow importing from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from google.cloud import firestore

COLLECTIONS = [
    "workspaces",
    "series",
    "occurrences",
    "check_ins",
    "notification_rules",
    "delivery_logs",
]


def get_client() -> firestore.Client:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "living-memories-488001")
    database = os.environ.get("LIVING_MEMORY_FIRESTORE_DATABASE", "living-memories-db")
    return firestore.Client(project=project, database=database)


def migrate_collection(db: firestore.Client, collection_name: str, dry_run: bool) -> int:
    """Migrate workspace_id → room_id in all docs of a collection. Returns count."""
    count = 0
    docs = db.collection(collection_name).stream()
    for doc in docs:
        data = doc.to_dict()
        if "workspace_id" in data and "room_id" not in data:
            count += 1
            if dry_run:
                print(f"  [dry-run] {collection_name}/{doc.id}: "
                      f"workspace_id={data['workspace_id']} → room_id")
            else:
                doc.reference.update({
                    "room_id": data["workspace_id"],
                    "workspace_id": firestore.DELETE_FIELD,
                })
                print(f"  migrated {collection_name}/{doc.id}")
        elif "workspace_id" in data and "room_id" in data:
            # Both exist — remove the old one
            if not dry_run:
                doc.reference.update({
                    "workspace_id": firestore.DELETE_FIELD,
                })
                print(f"  cleaned {collection_name}/{doc.id} (removed workspace_id)")
            else:
                print(f"  [dry-run] {collection_name}/{doc.id}: remove duplicate workspace_id")
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Migrate workspace_id → room_id in Firestore")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    db = get_client()
    total = 0

    for collection_name in COLLECTIONS:
        print(f"\n--- {collection_name} ---")
        count = migrate_collection(db, collection_name, args.dry_run)
        print(f"  {count} documents {'would be' if args.dry_run else ''} migrated")
        total += count

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Total: {total} documents migrated across {len(COLLECTIONS)} collections")


if __name__ == "__main__":
    main()
