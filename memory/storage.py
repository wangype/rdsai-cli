"""SQLite-backed storage for cross-session memory."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from memory.types import ConversationMemoryRecord, MemoryStatus, QueryMemoryRecord, SessionCheckpoint
from utils.logging import logger


def default_memory_db_path() -> Path:
    """Return the default persistent memory database path."""
    share_dir = Path.home() / ".rdsai-cli"
    share_dir.mkdir(parents=True, exist_ok=True)
    return share_dir / "memory.db"


class MemoryStorageError(RuntimeError):
    """Raised when persistent memory storage cannot complete an operation."""


class SQLiteMemoryStorage:
    """SQLite storage layer for query history, checkpoints, and conversation memory."""

    def __init__(self, path: Path | None = None):
        """Initialize SQLite storage and ensure the schema exists."""
        self.path = path or default_memory_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._initialize()
        except sqlite3.Error as exc:
            logger.warning("Persistent memory is unavailable: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection configured for row access."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        """Create memory tables if they do not already exist."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    sql TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_time REAL,
                    affected_rows INTEGER,
                    error_message TEXT,
                    database_name TEXT,
                    tags TEXT NOT NULL DEFAULT '[]'
                );

                CREATE INDEX IF NOT EXISTS idx_query_history_timestamp
                    ON query_history(timestamp);
                CREATE INDEX IF NOT EXISTS idx_query_history_database
                    ON query_history(database_name);

                CREATE TABLE IF NOT EXISTS session_checkpoints (
                    session_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    database_connection TEXT,
                    last_queries TEXT NOT NULL DEFAULT '[]',
                    user_preferences TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_session_checkpoints_timestamp
                    ON session_checkpoints(timestamp);

                CREATE TABLE IF NOT EXISTS conversation_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('preference', 'context', 'fact'))
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_memory_session
                    ON conversation_memory(session_id);
                CREATE INDEX IF NOT EXISTS idx_conversation_memory_key
                    ON conversation_memory(key);
                """
            )

    def save_query(self, record: QueryMemoryRecord) -> int:
        """Persist a SQL query history record and return its row id."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO query_history (
                        timestamp, sql, status, execution_time, affected_rows,
                        error_message, database_name, tags
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.timestamp,
                        record.sql,
                        record.status,
                        record.execution_time,
                        record.affected_rows,
                        record.error_message,
                        record.database_name,
                        json.dumps(record.tags),
                    ),
                )
                return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            logger.warning("Failed to save query memory: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc

    def get_recent_queries(self, limit: int = 10, database_name: str | None = None) -> list[QueryMemoryRecord]:
        """Return recent query history records."""
        if limit <= 0:
            return []
        try:
            with self._connect() as conn:
                if database_name:
                    rows = conn.execute(
                        """
                        SELECT * FROM query_history
                        WHERE database_name = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (database_name, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM query_history ORDER BY id DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Failed to load query memory: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc
        return [self._query_from_row(row) for row in reversed(rows)]

    def search_queries(self, pattern: str, limit: int = 20) -> list[QueryMemoryRecord]:
        """Search persisted SQL text with a case-insensitive LIKE match."""
        if not pattern.strip() or limit <= 0:
            return []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM query_history
                    WHERE lower(sql) LIKE lower(?)
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (f"%{pattern.strip()}%", limit),
                ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Failed to search query memory: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc
        return [self._query_from_row(row) for row in rows]

    def clear_queries(self) -> None:
        """Delete all persisted query history."""
        self._execute_delete("DELETE FROM query_history")

    def save_checkpoint(self, checkpoint: SessionCheckpoint) -> None:
        """Insert or replace a session checkpoint."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO session_checkpoints (
                        session_id, timestamp, database_connection, last_queries, user_preferences
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        timestamp = excluded.timestamp,
                        database_connection = excluded.database_connection,
                        last_queries = excluded.last_queries,
                        user_preferences = excluded.user_preferences
                    """,
                    (
                        checkpoint.session_id,
                        checkpoint.timestamp,
                        json.dumps(checkpoint.database_connection),
                        json.dumps(checkpoint.last_queries),
                        json.dumps(checkpoint.user_preferences),
                    ),
                )
        except sqlite3.Error as exc:
            logger.warning("Failed to save session checkpoint: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc

    def get_latest_checkpoint(self) -> SessionCheckpoint | None:
        """Return the latest session checkpoint, if any."""
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM session_checkpoints ORDER BY timestamp DESC LIMIT 1").fetchone()
        except sqlite3.Error as exc:
            logger.warning("Failed to load session checkpoint: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc
        return self._checkpoint_from_row(row) if row else None

    def save_conversation_memory(self, record: ConversationMemoryRecord) -> int:
        """Persist a conversation memory record and return its row id."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO conversation_memory (session_id, timestamp, key, value, type)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (record.session_id, record.timestamp, record.key, record.value, record.type),
                )
                return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            logger.warning("Failed to save conversation memory: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc

    def search_conversation_memory(self, pattern: str, limit: int = 20) -> list[ConversationMemoryRecord]:
        """Search conversation memory keys and values."""
        if not pattern.strip() or limit <= 0:
            return []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM conversation_memory
                    WHERE lower(key) LIKE lower(?) OR lower(value) LIKE lower(?)
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (f"%{pattern.strip()}%", f"%{pattern.strip()}%", limit),
                ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Failed to search conversation memory: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc
        return [self._conversation_from_row(row) for row in rows]

    def clear_conversation_memory(self) -> None:
        """Delete all persisted conversation memory."""
        self._execute_delete("DELETE FROM conversation_memory")

    def clear_all(self) -> None:
        """Delete all persisted memory."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM query_history")
                conn.execute("DELETE FROM session_checkpoints")
                conn.execute("DELETE FROM conversation_memory")
        except sqlite3.Error as exc:
            logger.warning("Failed to clear memory: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc

    def status(self) -> MemoryStatus:
        """Return storage availability and record counts."""
        try:
            with self._connect() as conn:
                query_count = self._count(conn, "query_history")
                checkpoint_count = self._count(conn, "session_checkpoints")
                conversation_count = self._count(conn, "conversation_memory")
                latest = conn.execute(
                    "SELECT session_id, timestamp FROM session_checkpoints ORDER BY timestamp DESC LIMIT 1"
                ).fetchone()
        except sqlite3.Error as exc:
            logger.warning("Failed to read memory status: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc
        return MemoryStatus(
            available=True,
            database_path=str(self.path),
            query_count=query_count,
            checkpoint_count=checkpoint_count,
            conversation_count=conversation_count,
            latest_session_id=latest["session_id"] if latest else None,
            latest_session_timestamp=latest["timestamp"] if latest else None,
        )

    def export(self) -> dict[str, Any]:
        """Export all memory tables as JSON-serializable data."""
        try:
            with self._connect() as conn:
                queries = [self._query_from_row(row).to_dict() for row in conn.execute("SELECT * FROM query_history")]
                checkpoints = [
                    self._checkpoint_from_row(row).to_dict()
                    for row in conn.execute("SELECT * FROM session_checkpoints")
                ]
                conversations = [
                    self._conversation_from_row(row).to_dict()
                    for row in conn.execute("SELECT * FROM conversation_memory")
                ]
        except sqlite3.Error as exc:
            logger.warning("Failed to export memory: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc
        return {
            "query_history": queries,
            "session_checkpoints": checkpoints,
            "conversation_memory": conversations,
        }

    def _execute_delete(self, sql: str) -> None:
        """Execute a delete statement with storage error handling."""
        try:
            with self._connect() as conn:
                conn.execute(sql)
        except sqlite3.Error as exc:
            logger.warning("Failed to delete memory: {error}", error=exc)
            raise MemoryStorageError(str(exc)) from exc

    @staticmethod
    def _count(conn: sqlite3.Connection, table: str) -> int:
        """Return the number of rows in a table."""
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])

    @staticmethod
    def _loads_json(value: str | None, fallback: Any) -> Any:
        """Decode JSON text and return fallback on invalid data."""
        if value is None:
            return fallback
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback

    @classmethod
    def _query_from_row(cls, row: sqlite3.Row) -> QueryMemoryRecord:
        """Build a query memory record from a SQLite row."""
        tags = cls._loads_json(row["tags"], [])
        if not isinstance(tags, list):
            tags = []
        return QueryMemoryRecord(
            id=row["id"],
            timestamp=row["timestamp"],
            sql=row["sql"],
            status=row["status"],
            execution_time=row["execution_time"],
            affected_rows=row["affected_rows"],
            error_message=row["error_message"],
            database_name=row["database_name"],
            tags=[str(tag) for tag in tags],
        )

    @classmethod
    def _checkpoint_from_row(cls, row: sqlite3.Row) -> SessionCheckpoint:
        """Build a session checkpoint from a SQLite row."""
        database_connection = cls._loads_json(row["database_connection"], None)
        last_queries = cls._loads_json(row["last_queries"], [])
        user_preferences = cls._loads_json(row["user_preferences"], {})
        return SessionCheckpoint(
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            database_connection=database_connection if isinstance(database_connection, dict) else None,
            last_queries=last_queries if isinstance(last_queries, list) else [],
            user_preferences=user_preferences if isinstance(user_preferences, dict) else {},
        )

    @staticmethod
    def _conversation_from_row(row: sqlite3.Row) -> ConversationMemoryRecord:
        """Build a conversation memory record from a SQLite row."""
        return ConversationMemoryRecord(
            id=row["id"],
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            key=row["key"],
            value=row["value"],
            type=row["type"],
        )


class InMemoryMemoryStorage:
    """In-process fallback storage used when SQLite is unavailable."""

    def __init__(self, path: Path | None = None):
        """Initialize empty fallback memory storage."""
        self.path = path or default_memory_db_path()
        self._queries: list[QueryMemoryRecord] = []
        self._checkpoints: dict[str, SessionCheckpoint] = {}
        self._conversations: list[ConversationMemoryRecord] = []

    def save_query(self, record: QueryMemoryRecord) -> int:
        """Store a SQL query record in process memory."""
        record.id = len(self._queries) + 1
        self._queries.append(record)
        return record.id

    def get_recent_queries(self, limit: int = 10, database_name: str | None = None) -> list[QueryMemoryRecord]:
        """Return recent in-memory query records."""
        queries: Iterable[QueryMemoryRecord] = self._queries
        if database_name:
            queries = [record for record in queries if record.database_name == database_name]
        return list(queries)[-limit:] if limit > 0 else []

    def search_queries(self, pattern: str, limit: int = 20) -> list[QueryMemoryRecord]:
        """Search in-memory SQL text."""
        pattern_lower = pattern.lower()
        matches = [record for record in reversed(self._queries) if pattern_lower in record.sql.lower()]
        return matches[:limit]

    def clear_queries(self) -> None:
        """Clear in-memory query history."""
        self._queries.clear()

    def save_checkpoint(self, checkpoint: SessionCheckpoint) -> None:
        """Store a checkpoint in process memory."""
        self._checkpoints[checkpoint.session_id] = checkpoint

    def get_latest_checkpoint(self) -> SessionCheckpoint | None:
        """Return the latest in-memory checkpoint."""
        if not self._checkpoints:
            return None
        return max(self._checkpoints.values(), key=lambda checkpoint: checkpoint.timestamp)

    def save_conversation_memory(self, record: ConversationMemoryRecord) -> int:
        """Store conversation memory in process memory."""
        record.id = len(self._conversations) + 1
        self._conversations.append(record)
        return record.id

    def search_conversation_memory(self, pattern: str, limit: int = 20) -> list[ConversationMemoryRecord]:
        """Search in-memory conversation memory."""
        pattern_lower = pattern.lower()
        matches = [
            record
            for record in reversed(self._conversations)
            if pattern_lower in record.key.lower() or pattern_lower in record.value.lower()
        ]
        return matches[:limit]

    def clear_conversation_memory(self) -> None:
        """Clear in-memory conversation memory."""
        self._conversations.clear()

    def clear_all(self) -> None:
        """Clear all in-memory data."""
        self._queries.clear()
        self._checkpoints.clear()
        self._conversations.clear()

    def status(self) -> MemoryStatus:
        """Return fallback memory status."""
        latest = self.get_latest_checkpoint()
        return MemoryStatus(
            available=False,
            database_path=str(self.path),
            query_count=len(self._queries),
            checkpoint_count=len(self._checkpoints),
            conversation_count=len(self._conversations),
            latest_session_id=latest.session_id if latest else None,
            latest_session_timestamp=latest.timestamp if latest else None,
            error="SQLite unavailable; using in-memory fallback",
        )

    def export(self) -> dict[str, Any]:
        """Export all in-memory data."""
        return {
            "query_history": [record.to_dict() for record in self._queries],
            "session_checkpoints": [record.to_dict() for record in self._checkpoints.values()],
            "conversation_memory": [record.to_dict() for record in self._conversations],
        }


def create_memory_storage(path: Path | None = None) -> SQLiteMemoryStorage | InMemoryMemoryStorage:
    """Create SQLite storage, falling back to in-memory storage on failure."""
    try:
        return SQLiteMemoryStorage(path)
    except MemoryStorageError:
        return InMemoryMemoryStorage(path)
