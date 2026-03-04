"""Cleanup — delete expired memories from Firestore and purge GCS attachments."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime

from dates import today as _today
from memory import Memory
from storage import delete_from_gcs

logger = logging.getLogger(__name__)


def purge_attachments(mem: Memory) -> None:
    """Delete each attachment URL from GCS."""
    if not mem.attachments:
        return
    for url in mem.attachments:
        try:
            delete_from_gcs(url)
        except Exception:
            logger.warning("Failed to delete attachment: %s", url)


def cleanup_firestore(today: date | None = None) -> list[str]:
    """Delete expired memories from Firestore and purge their GCS attachments.

    Returns a list of deleted Firestore document IDs.
    """
    import firestore_storage

    if today is None:
        today = _today()

    deleted_pairs = firestore_storage.delete_expired(today)
    for _, mem in deleted_pairs:
        purge_attachments(mem)
    return [doc_id for doc_id, _ in deleted_pairs]


def cleanup_pages(now: datetime | None = None) -> list[str]:
    """Hard-delete pages whose delete_after has passed."""
    import page_storage

    if now is None:
        now = page_storage._utcnow()

    db = page_storage._get_client()
    docs = (
        db.collection(page_storage.PAGES_COLLECTION)
        .where("delete_after", "<=", now)
        .stream()
    )
    deleted_slugs = []
    for doc in docs:
        slug = doc.id
        page_storage.delete_page(slug)
        deleted_slugs.append(slug)
    return deleted_slugs


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the cleanup module."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        description="Delete expired memories and purge attachments",
    )
    parser.add_argument(
        "--today", type=date.fromisoformat, default=None,
        help="Override today's date for testing",
    )
    args = parser.parse_args(argv)
    today = args.today or _today()

    try:
        logger.info("Starting memory cleanup (today=%s)...", today)
        deleted_ids = cleanup_firestore(today)
        for doc_id in deleted_ids:
            print(f"Deleted Firestore doc: {doc_id}")
        logger.info("Memory cleanup done: %d deleted.", len(deleted_ids))
    except Exception:
        logger.exception("Memory cleanup failed")
        sys.exit(1)

    try:
        logger.info("Starting page cleanup...")
        deleted_slugs = cleanup_pages()
        for slug in deleted_slugs:
            print(f"Deleted soft-deleted page: {slug}")
        logger.info("Page cleanup done: %d deleted.", len(deleted_slugs))
    except Exception:
        logger.exception("Page cleanup failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
