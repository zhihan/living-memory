"""Tests for the cleanup module."""

from datetime import date
from pathlib import Path
from unittest import mock

import pytest

from cleanup import cleanup, find_expired
from memory import Memory


def _write_memory(path: Path, mem: Memory) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mem.dump(path)


@pytest.fixture()
def memories_dir(tmp_path: Path) -> Path:
    return tmp_path / "memories"


class TestFindExpired:
    def test_finds_expired_skips_valid(self, memories_dir: Path) -> None:
        today = date(2026, 3, 1)
        expired_mem = Memory(
            target=date(2026, 2, 1),
            expires=date(2026, 2, 15),
            content="old event",
            title="Old",
        )
        valid_mem = Memory(
            target=date(2026, 4, 1),
            expires=date(2026, 4, 15),
            content="future event",
            title="Future",
        )
        _write_memory(memories_dir / "old.md", expired_mem)
        _write_memory(memories_dir / "future.md", valid_mem)

        result = find_expired(memories_dir, today)

        assert len(result) == 1
        assert result[0][0].name == "old.md"
        assert result[0][1].title == "Old"

    def test_no_expired(self, memories_dir: Path) -> None:
        today = date(2026, 1, 1)
        mem = Memory(
            target=date(2026, 6, 1),
            expires=date(2026, 6, 30),
            content="future",
        )
        _write_memory(memories_dir / "future.md", mem)

        result = find_expired(memories_dir, today)

        assert result == []


class TestCleanup:
    @mock.patch("cleanup.subprocess")
    def test_deletes_expired_files(
        self, mock_sp: mock.Mock, memories_dir: Path,
    ) -> None:
        today = date(2026, 3, 1)
        expired = Memory(
            target=date(2026, 2, 1),
            expires=date(2026, 2, 15),
            content="old",
            title="Old",
        )
        _write_memory(memories_dir / "old.md", expired)

        deleted = cleanup(memories_dir, today, push=False)

        assert len(deleted) == 1
        assert not (memories_dir / "old.md").exists()

    @mock.patch("cleanup.delete_from_gcs")
    @mock.patch("cleanup.subprocess")
    def test_purges_attachments(
        self,
        mock_sp: mock.Mock,
        mock_delete_gcs: mock.Mock,
        memories_dir: Path,
    ) -> None:
        today = date(2026, 3, 1)
        urls = [
            "https://storage.googleapis.com/bucket/a.png",
            "https://storage.googleapis.com/bucket/b.png",
        ]
        expired = Memory(
            target=date(2026, 2, 1),
            expires=date(2026, 2, 15),
            content="old",
            title="Old",
            attachments=urls,
        )
        _write_memory(memories_dir / "old.md", expired)

        cleanup(memories_dir, today, push=False)

        assert mock_delete_gcs.call_count == 2
        mock_delete_gcs.assert_any_call(urls[0])
        mock_delete_gcs.assert_any_call(urls[1])

    @mock.patch("cleanup.subprocess")
    def test_skips_non_expired(
        self, mock_sp: mock.Mock, memories_dir: Path,
    ) -> None:
        today = date(2026, 1, 1)
        mem = Memory(
            target=date(2026, 6, 1),
            expires=date(2026, 6, 30),
            content="future",
            title="Future",
        )
        _write_memory(memories_dir / "future.md", mem)

        deleted = cleanup(memories_dir, today, push=False)

        assert deleted == []
        assert (memories_dir / "future.md").exists()

    def test_no_expired_noop(self, memories_dir: Path) -> None:
        memories_dir.mkdir(parents=True, exist_ok=True)

        deleted = cleanup(memories_dir, date(2026, 1, 1), push=False)

        assert deleted == []
