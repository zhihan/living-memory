"""Tests for the publisher module's Firestore path."""

from datetime import date
from unittest.mock import patch

from memory import Memory
from publisher import load_memories_from_firestore


@patch("firestore_storage.load_all_memories")
def test_load_memories_from_firestore_sorted(mock_load_all):
    mem1 = Memory(target=date(2026, 3, 5), expires=date(2026, 4, 5),
                  content="Event A", title="A")
    mem2 = Memory(target=date(2026, 3, 1), expires=date(2026, 4, 1),
                  content="Event B", title="B")
    mock_load_all.return_value = [("d1", mem1), ("d2", mem2)]

    results = load_memories_from_firestore(date(2026, 2, 18))

    # Should be sorted by target date
    assert results[0].title == "B"
    assert results[1].title == "A"


@patch("firestore_storage.load_all_memories")
def test_load_memories_from_firestore_filters_expired(mock_load_all):
    mem1 = Memory(target=date(2026, 3, 5), expires=date(2026, 4, 5),
                  content="Event A", title="A")
    expired = Memory(target=date(2026, 1, 1), expires=date(2026, 1, 31),
                     content="Old", title="Old")
    mock_load_all.return_value = [("d1", mem1), ("d2", expired)]

    results = load_memories_from_firestore(date(2026, 2, 18))

    assert len(results) == 1
    assert results[0].title == "A"
