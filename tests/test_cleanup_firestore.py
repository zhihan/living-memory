"""Tests for Firestore-based cleanup."""

from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock

from memory import Memory
from cleanup import cleanup_firestore, cleanup_pages


def _make_memory(**kwargs) -> Memory:
    defaults = dict(
        target=date(2026, 2, 1),
        expires=date(2026, 2, 15),
        content="old event",
        title="Old",
    )
    defaults.update(kwargs)
    return Memory(**defaults)


@patch("cleanup.purge_attachments")
@patch("firestore_storage.delete_expired")
def test_cleanup_firestore_purges_and_deletes(mock_delete_expired, mock_purge):
    expired_mem = _make_memory(
        attachments=["https://storage.googleapis.com/bucket/a.png"],
    )
    mock_delete_expired.return_value = [("doc1", expired_mem)]

    deleted = cleanup_firestore(today=date(2026, 3, 1))

    assert deleted == ["doc1"]
    mock_purge.assert_called_once_with(expired_mem)


@patch("cleanup.purge_attachments")
@patch("firestore_storage.delete_expired")
def test_cleanup_firestore_no_expired(mock_delete_expired, mock_purge):
    mock_delete_expired.return_value = []

    deleted = cleanup_firestore(today=date(2026, 1, 1))

    assert deleted == []
    mock_purge.assert_not_called()


# ---------------------------------------------------------------------------
# cleanup_pages
# ---------------------------------------------------------------------------

@patch("page_storage.delete_page")
@patch("page_storage._get_client")
def test_cleanup_pages(mock_gc, mock_del):
    mock_db = MagicMock()
    mock_gc.return_value = mock_db

    past = datetime(2026, 1, 1, tzinfo=timezone.utc)
    doc1 = MagicMock()
    doc1.id = "old-page"
    mock_db.collection.return_value.where.return_value.stream.return_value = [doc1]

    now = datetime(2026, 2, 24, tzinfo=timezone.utc)
    deleted = cleanup_pages(now=now)

    assert deleted == ["old-page"]
    mock_del.assert_called_once_with("old-page")


@patch("page_storage._get_client")
def test_cleanup_pages_skips_active(mock_gc):
    mock_db = MagicMock()
    mock_gc.return_value = mock_db

    # No documents match the query (all pages are active)
    mock_db.collection.return_value.where.return_value.stream.return_value = []

    now = datetime(2026, 2, 24, tzinfo=timezone.utc)
    deleted = cleanup_pages(now=now)

    assert deleted == []
