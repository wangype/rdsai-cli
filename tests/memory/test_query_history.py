"""Tests for persistent query history."""

from database.history import PersistentQueryHistory
from memory.storage import SQLiteMemoryStorage


def test_persistent_query_history_records_and_searches(tmp_path):
    """PersistentQueryHistory should mirror recorded queries to storage."""
    storage = SQLiteMemoryStorage(tmp_path / "memory.db")
    history = PersistentQueryHistory(max_entries=10, storage=storage)

    history.record_query(
        "SELECT * FROM users",
        status="success",
        execution_time=0.2,
        affected_rows=3,
        database_name="app",
        tags=["manual"],
    )

    recent = history.get_recent_queries(5)
    assert len(recent) == 1
    assert recent[0].sql == "SELECT * FROM users"
    assert recent[0].database_name == "app"

    matches = history.search("users")
    assert len(matches) == 1
    assert matches[0].tags == ["manual"]


def test_persistent_query_history_hydrates_recent_entries(tmp_path):
    """PersistentQueryHistory should load recent storage entries on startup."""
    storage = SQLiteMemoryStorage(tmp_path / "memory.db")
    first = PersistentQueryHistory(max_entries=10, storage=storage)
    first.record_query("SELECT 1", status="success")

    second = PersistentQueryHistory(max_entries=10, storage=storage)
    assert second.get_recent_successful_queries(1) == ["SELECT 1"]
