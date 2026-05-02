"""SQL query history management."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from memory.storage import InMemoryMemoryStorage, SQLiteMemoryStorage, create_memory_storage
from memory.types import QueryMemoryRecord
from utils.logging import logger


@dataclass
class QueryHistoryEntry:
    """Represents a single query history entry."""

    timestamp: str
    sql: str
    status: str  # 'success' or 'error'
    execution_time: float | None = None
    affected_rows: int | None = None
    error_message: str | None = None
    database_name: str | None = None
    tags: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryHistoryEntry:
        """Create from dictionary representation."""
        return cls(**data)


class QueryHistory:
    """Manages SQL query execution history using deque for efficient operations."""

    def __init__(self, max_entries: int = 100):
        self._entries: deque[QueryHistoryEntry] = deque(maxlen=max_entries)
        self._max_entries = max_entries

    def record_query(
        self,
        sql: str,
        status: str = "success",
        execution_time: float | None = None,
        affected_rows: int | None = None,
        error_message: str | None = None,
        database_name: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Record a query execution in history."""
        entry = QueryHistoryEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            sql=sql.strip(),
            status=status,
            execution_time=execution_time,
            affected_rows=affected_rows,
            error_message=error_message,
            database_name=database_name,
            tags=tags or [],
        )
        self._entries.append(entry)
        logger.debug(f"Recorded query in history: {sql[:50]}...")

    def get_recent_queries(self, limit: int = 10) -> list[QueryHistoryEntry]:
        """Get recent query history entries."""
        if limit <= 0 or not self._entries:
            return []
        return list(self._entries)[-limit:]

    def get_recent_successful_queries(self, limit: int = 5) -> list[str]:
        """Get recent successful SQL queries."""
        successful_queries = []
        for entry in reversed(self._entries):
            if entry.status == "success":
                successful_queries.append(entry.sql)
                if len(successful_queries) >= limit:
                    break
        return successful_queries

    def get_all_entries(self) -> list[QueryHistoryEntry]:
        """Get all history entries as a list."""
        return list(self._entries)

    def clear_history(self) -> None:
        """Clear all query history."""
        self._entries.clear()
        logger.info("Query history cleared")

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about query history."""
        if not self._entries:
            return {
                "total_queries": 0,
                "successful_queries": 0,
                "failed_queries": 0,
                "success_rate": 0.0,
                "average_execution_time": None,
            }

        successful_count = sum(1 for entry in self._entries if entry.status == "success")
        failed_count = len(self._entries) - successful_count

        timed_queries = [entry for entry in self._entries if entry.execution_time is not None]
        avg_time = None
        if timed_queries:
            avg_time = sum(entry.execution_time for entry in timed_queries) / len(timed_queries)

        return {
            "total_queries": len(self._entries),
            "successful_queries": successful_count,
            "failed_queries": failed_count,
            "success_rate": (successful_count / len(self._entries)) * 100,
            "average_execution_time": avg_time,
        }

    def find_queries_by_pattern(self, pattern: str, limit: int = 10) -> list[QueryHistoryEntry]:
        """Find queries matching a pattern (case-insensitive)."""
        pattern_lower = pattern.lower()
        matches = []
        for entry in reversed(self._entries):
            if pattern_lower in entry.sql.lower():
                matches.append(entry)
                if len(matches) >= limit:
                    break
        return matches

    def search(self, pattern: str, limit: int = 10) -> list[QueryHistoryEntry]:
        """Search query history by SQL keyword."""
        return self.find_queries_by_pattern(pattern, limit)

    def get_queries_by_status(self, status: str, limit: int = 10) -> list[QueryHistoryEntry]:
        """Get queries with specific status."""
        matches = []
        for entry in reversed(self._entries):
            if entry.status == status:
                matches.append(entry)
                if len(matches) >= limit:
                    break
        return matches

    def to_dict(self) -> dict[str, Any]:
        """Export history to dictionary format."""
        return {"max_entries": self._max_entries, "entries": [entry.to_dict() for entry in self._entries]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryHistory:
        """Import history from dictionary format."""
        max_entries = data.get("max_entries", 100)
        instance = cls(max_entries=max_entries)
        entries = data.get("entries", [])
        for entry_data in entries[-max_entries:]:
            entry = QueryHistoryEntry.from_dict(entry_data)
            instance._entries.append(entry)
        return instance


class PersistentQueryHistory(QueryHistory):
    """Query history that mirrors entries to persistent memory storage."""

    def __init__(
        self,
        max_entries: int = 100,
        storage: SQLiteMemoryStorage | InMemoryMemoryStorage | None = None,
    ):
        """Initialize persistent query history with a bounded in-memory cache."""
        super().__init__(max_entries=max_entries)
        self._storage = storage or create_memory_storage()
        self._hydrate_recent_entries()

    def record_query(
        self,
        sql: str,
        status: str = "success",
        execution_time: float | None = None,
        affected_rows: int | None = None,
        error_message: str | None = None,
        database_name: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Record a query execution in memory and persistent storage."""
        if database_name is None:
            database_name = self._get_current_database_name()

        super().record_query(
            sql=sql,
            status=status,
            execution_time=execution_time,
            affected_rows=affected_rows,
            error_message=error_message,
            database_name=database_name,
            tags=tags,
        )

        entry = self._entries[-1]
        try:
            self._storage.save_query(
                QueryMemoryRecord(
                    timestamp=entry.timestamp,
                    sql=entry.sql,
                    status=entry.status,
                    execution_time=entry.execution_time,
                    affected_rows=entry.affected_rows,
                    error_message=entry.error_message,
                    database_name=entry.database_name,
                    tags=entry.tags or [],
                )
            )
        except Exception as exc:
            logger.warning("Failed to persist query history; continuing in memory: {error}", error=exc)

    def get_recent_queries(self, limit: int = 10) -> list[QueryHistoryEntry]:
        """Get recent query history entries, preferring persistent storage."""
        if limit <= 0:
            return []
        try:
            records = self._storage.get_recent_queries(limit=limit)
            if records:
                return [self._entry_from_record(record) for record in records]
        except Exception as exc:
            logger.debug("Failed to load persisted query history: {error}", error=exc)
        return super().get_recent_queries(limit)

    def get_all_entries(self) -> list[QueryHistoryEntry]:
        """Get cached history entries as a list."""
        return list(self._entries)

    def clear_history(self) -> None:
        """Clear in-memory and persistent query history."""
        super().clear_history()
        try:
            self._storage.clear_queries()
        except Exception as exc:
            logger.warning("Failed to clear persisted query history: {error}", error=exc)

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about query history."""
        try:
            status = self._storage.status()
            if status.query_count > len(self._entries):
                entries = self.get_recent_queries(status.query_count)
                return self._statistics_for_entries(entries)
        except Exception as exc:
            logger.debug("Failed to read persisted query statistics: {error}", error=exc)
        return super().get_statistics()

    def search(self, pattern: str, limit: int = 10) -> list[QueryHistoryEntry]:
        """Search persistent query history by SQL keyword."""
        try:
            records = self._storage.search_queries(pattern, limit=limit)
            return [self._entry_from_record(record) for record in records]
        except Exception as exc:
            logger.debug("Failed to search persisted query history: {error}", error=exc)
        return super().search(pattern, limit)

    def find_queries_by_pattern(self, pattern: str, limit: int = 10) -> list[QueryHistoryEntry]:
        """Find queries matching a pattern (case-insensitive)."""
        return self.search(pattern, limit)

    def _hydrate_recent_entries(self) -> None:
        """Load recent persisted entries into the bounded in-memory cache."""
        try:
            for record in self._storage.get_recent_queries(limit=self._max_entries):
                self._entries.append(self._entry_from_record(record))
        except Exception as exc:
            logger.debug("Failed to hydrate persistent query history: {error}", error=exc)

    @staticmethod
    def _entry_from_record(record: QueryMemoryRecord) -> QueryHistoryEntry:
        """Convert a persistent query record to a history entry."""
        return QueryHistoryEntry(
            timestamp=record.timestamp,
            sql=record.sql,
            status=record.status,
            execution_time=record.execution_time,
            affected_rows=record.affected_rows,
            error_message=record.error_message,
            database_name=record.database_name,
            tags=record.tags,
        )

    @staticmethod
    def _statistics_for_entries(entries: list[QueryHistoryEntry]) -> dict[str, Any]:
        """Compute query statistics from a list of entries."""
        if not entries:
            return {
                "total_queries": 0,
                "successful_queries": 0,
                "failed_queries": 0,
                "success_rate": 0.0,
                "average_execution_time": None,
            }

        successful_count = sum(1 for entry in entries if entry.status == "success")
        failed_count = len(entries) - successful_count
        timed_queries = [entry for entry in entries if entry.execution_time is not None]
        avg_time = None
        if timed_queries:
            avg_time = sum(entry.execution_time for entry in timed_queries if entry.execution_time is not None) / len(
                timed_queries
            )

        return {
            "total_queries": len(entries),
            "successful_queries": successful_count,
            "failed_queries": failed_count,
            "success_rate": (successful_count / len(entries)) * 100,
            "average_execution_time": avg_time,
        }

    @staticmethod
    def _get_current_database_name() -> str | None:
        """Return the current database name from the active service when available."""
        try:
            from database.service import get_service

            db_service = get_service()
            if db_service and db_service.is_connected():
                return db_service.get_connection_info().get("database")
        except Exception:
            return None
        return None
