"""Cleanup — delete expired memory files and purge GCS attachments."""

from __future__ import annotations

import argparse
import logging
import subprocess
from datetime import date
from pathlib import Path

from memory import Memory
from storage import delete_from_gcs

logger = logging.getLogger(__name__)


def find_expired(
    memories_dir: Path,
    today: date,
) -> list[tuple[Path, Memory]]:
    """Scan *memories_dir* and return (path, memory) pairs that are expired."""
    expired: list[tuple[Path, Memory]] = []
    for path in sorted(memories_dir.glob("*.md")):
        mem = Memory.load(path)
        if mem.is_expired(today):
            expired.append((path, mem))
    return expired


def purge_attachments(mem: Memory) -> None:
    """Delete each attachment URL from GCS."""
    if not mem.attachments:
        return
    for url in mem.attachments:
        try:
            delete_from_gcs(url)
        except Exception:
            logger.warning("Failed to delete attachment: %s", url)


def cleanup(
    memories_dir: Path,
    today: date,
    push: bool = True,
) -> list[Path]:
    """Find expired memories, purge attachments, delete files, and commit.

    Returns the list of deleted file paths.
    """
    expired = find_expired(memories_dir, today)
    if not expired:
        return []

    deleted: list[Path] = []
    for path, mem in expired:
        purge_attachments(mem)
        path.unlink()
        deleted.append(path)

    # Git commit (and optionally push) the removals.
    for path in deleted:
        subprocess.run(["git", "add", str(path)], check=True)
    names = ", ".join(p.name for p in deleted)
    subprocess.run(
        ["git", "commit", "-m", f"Cleanup expired memories: {names}"],
        check=True,
    )
    if push:
        subprocess.run(["git", "push"], check=True)

    return deleted


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the cleanup module."""
    parser = argparse.ArgumentParser(
        description="Delete expired memories and purge attachments",
    )
    parser.add_argument(
        "--memories-dir", type=Path, default=Path("memories"),
    )
    parser.add_argument(
        "--today", type=date.fromisoformat, default=None,
        help="Override today's date for testing",
    )
    parser.add_argument(
        "--no-push", action="store_true",
        help="Skip git push",
    )
    args = parser.parse_args(argv)

    today = args.today or date.today()
    deleted = cleanup(args.memories_dir, today, push=not args.no_push)
    for path in deleted:
        print(f"Deleted: {path}")


if __name__ == "__main__":
    main()
