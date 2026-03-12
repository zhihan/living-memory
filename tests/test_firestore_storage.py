"""Tests for the Firestore storage module."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch, call

from memory import Memory
import firestore_storage


def _make_memory(**kwargs) -> Memory:
    defaults = dict(
        target=date(2026, 3, 15),
        expires=date(2026, 4, 15),
        content="Test event.",
        title="Test",
    )
    defaults.update(kwargs)
    return Memory(**defaults)


def _mock_doc(doc_id: str, data: dict) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    doc.reference = MagicMock()
    return doc


class TestSaveMemory:
    @patch("firestore_storage._get_client")
    def test_create_new(self, mock_get_client):
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_ref = MagicMock()
        mock_ref.id = "new-doc-123"
        mock_db.collection.return_value.add.return_value = (None, mock_ref)

        mem = _make_memory()
        doc_id = firestore_storage.save_memory(mem)

        assert doc_id == "new-doc-123"
        mock_db.collection.return_value.add.assert_called_once_with(mem.to_dict())

    @patch("firestore_storage._get_client")
    def test_update_existing(self, mock_get_client):
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        mem = _make_memory()
        doc_id = firestore_storage.save_memory(mem, doc_id="existing-456")

        assert doc_id == "existing-456"
        mock_db.collection.return_value.document.assert_called_once_with("existing-456")
        mock_db.collection.return_value.document.return_value.set.assert_called_once_with(
            mem.to_dict()
        )



class TestLoadAllMemories:
    @patch("firestore_storage._get_client")
    def test_returns_all(self, mock_get_client):
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        mem1 = _make_memory(title="A")
        mem2 = _make_memory(title="B")

        docs = [
            _mock_doc("d1", mem1.to_dict()),
            _mock_doc("d2", mem2.to_dict()),
        ]
        mock_db.collection.return_value.stream.return_value = docs

        results = firestore_storage.load_all_memories()
        assert len(results) == 2


class TestDeleteMemory:
    @patch("firestore_storage._get_client")
    def test_deletes(self, mock_get_client):
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        firestore_storage.delete_memory("doc-to-delete")

        mock_db.collection.return_value.document.assert_called_once_with("doc-to-delete")
        mock_db.collection.return_value.document.return_value.delete.assert_called_once()


class TestDeleteExpired:
    @patch("firestore_storage._get_client")
    def test_deletes_expired_only(self, mock_get_client):
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        valid = _make_memory(expires=date(2026, 4, 15), title="Valid")
        expired = _make_memory(expires=date(2026, 2, 1), title="Expired")

        valid_doc = _mock_doc("d1", valid.to_dict())
        expired_doc = _mock_doc("d2", expired.to_dict())
        mock_db.collection.return_value.stream.return_value = [valid_doc, expired_doc]

        deleted = firestore_storage.delete_expired(today=date(2026, 3, 1))

        assert len(deleted) == 1
        assert deleted[0][0] == "d2"
        expired_doc.reference.delete.assert_called_once()
        valid_doc.reference.delete.assert_not_called()



class TestGetClient:
    @patch("google.cloud.firestore.Client")
    def test_default_database(self, mock_client_cls, monkeypatch):
        monkeypatch.delenv("LIVING_MEMORY_FIRESTORE_DATABASE", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        firestore_storage._get_client()
        mock_client_cls.assert_called_once_with()

    @patch("google.cloud.firestore.Client")
    def test_custom_database(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("LIVING_MEMORY_FIRESTORE_DATABASE", "living-memories-db")
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        firestore_storage._get_client()
        mock_client_cls.assert_called_once_with(database="living-memories-db")

    @patch("google.cloud.firestore.Client")
    def test_custom_database_and_project(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("LIVING_MEMORY_FIRESTORE_DATABASE", "living-memories-db")
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
        firestore_storage._get_client()
        mock_client_cls.assert_called_once_with(
            database="living-memories-db", project="my-project",
        )

    @patch("google.cloud.firestore.Client")
    def test_project_only(self, mock_client_cls, monkeypatch):
        monkeypatch.delenv("LIVING_MEMORY_FIRESTORE_DATABASE", raising=False)
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
        firestore_storage._get_client()
        mock_client_cls.assert_called_once_with(project="my-project")
