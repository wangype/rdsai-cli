"""Tests for memory storage."""

from memory.storage import SQLiteMemoryStorage
from memory.types import ConversationMemoryRecord, QueryMemoryRecord, SessionCheckpoint


def test_sqlite_storage_persists_queries(tmp_path):
    """SQLite storage should persist and search query history."""
    storage = SQLiteMemoryStorage(tmp_path / "memory.db")

    storage.save_query(
        QueryMemoryRecord(
            timestamp="2026-05-02 10:00:00",
            sql="SELECT * FROM users",
            status="success",
            execution_time=0.1,
            affected_rows=2,
            database_name="app",
            tags=["select"],
        )
    )

    recent = storage.get_recent_queries(limit=10)
    assert len(recent) == 1
    assert recent[0].sql == "SELECT * FROM users"
    assert recent[0].database_name == "app"
    assert recent[0].tags == ["select"]

    matches = storage.search_queries("users")
    assert len(matches) == 1
    assert matches[0].sql == "SELECT * FROM users"


def test_sqlite_storage_checkpoint_and_export(tmp_path):
    """SQLite storage should persist checkpoints and export all tables."""
    storage = SQLiteMemoryStorage(tmp_path / "memory.db")

    storage.save_checkpoint(
        SessionCheckpoint(
            session_id="session-1",
            timestamp="2026-05-02 10:00:00",
            database_connection={"engine": "mysql", "database": "app"},
            last_queries=[{"sql": "SELECT 1", "status": "success"}],
            user_preferences={"recent_successful_query_count": 1},
        )
    )
    storage.save_conversation_memory(
        ConversationMemoryRecord(
            session_id="session-1",
            timestamp="2026-05-02 10:01:00",
            key="preferred_table",
            value="users",
            type="preference",
        )
    )

    checkpoint = storage.get_latest_checkpoint()
    assert checkpoint is not None
    assert checkpoint.session_id == "session-1"
    assert checkpoint.database_connection == {"engine": "mysql", "database": "app"}

    status = storage.status()
    assert status.available is True
    assert status.checkpoint_count == 1
    assert status.conversation_count == 1

    exported = storage.export()
    assert exported["session_checkpoints"][0]["session_id"] == "session-1"
    assert exported["conversation_memory"][0]["key"] == "preferred_table"


def test_sqlite_storage_clear(tmp_path):
    """SQLite storage should clear selected memory tables."""
    storage = SQLiteMemoryStorage(tmp_path / "memory.db")
    storage.save_query(QueryMemoryRecord(timestamp="t", sql="SELECT 1", status="success"))
    storage.save_checkpoint(SessionCheckpoint(session_id="s", timestamp="t"))

    storage.clear_queries()
    assert storage.status().query_count == 0
    assert storage.status().checkpoint_count == 1

    storage.clear_all()
    assert storage.status().checkpoint_count == 0
