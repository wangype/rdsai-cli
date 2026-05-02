"""Tests for memory manager."""

from memory.manager import MemoryManager
from memory.storage import SQLiteMemoryStorage
from memory.types import QueryMemoryRecord, SessionCheckpoint


def test_manager_build_context_from_checkpoint_and_queries(tmp_path):
    """MemoryManager should build compact context from persisted memory."""
    storage = SQLiteMemoryStorage(tmp_path / "memory.db")
    storage.save_checkpoint(
        SessionCheckpoint(
            session_id="old-session",
            timestamp="2026-05-02 10:00:00",
            database_connection={"engine": "mysql", "database": "app", "host": "localhost"},
            last_queries=[{"sql": "SELECT * FROM users", "status": "success"}],
        )
    )
    storage.save_query(
        QueryMemoryRecord(
            timestamp="2026-05-02 10:01:00",
            sql="SELECT count(*) FROM users",
            status="success",
            database_name="app",
        )
    )

    manager = MemoryManager(session_id="new-session", storage=storage)
    context = manager.build_context(current_database="app")

    assert "Previous session" in context
    assert "SELECT * FROM users" in context
    assert "SELECT count(*) FROM users" in context

    assert manager.build_context(current_database="app") == ""


def test_manager_search_and_clear_history(tmp_path):
    """MemoryManager should search and clear query history."""
    storage = SQLiteMemoryStorage(tmp_path / "memory.db")
    storage.save_query(QueryMemoryRecord(timestamp="t", sql="SELECT * FROM orders", status="success"))
    manager = MemoryManager(session_id="session", storage=storage)

    results = manager.search("orders")
    assert len(results["query_history"]) == 1

    manager.clear_history()
    assert manager.status().query_count == 0
