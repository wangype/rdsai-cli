"""High-level persistent memory management."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from memory.storage import InMemoryMemoryStorage, SQLiteMemoryStorage, create_memory_storage
from memory.types import ConversationMemoryRecord, MemoryStatus, SessionCheckpoint
from utils.logging import logger


class MemoryManager:
    """Coordinates persistent memory loading, saving, and context injection."""

    def __init__(
        self,
        session_id: str,
        storage: SQLiteMemoryStorage | InMemoryMemoryStorage | None = None,
        db_path: Path | None = None,
    ):
        """Initialize a memory manager for a CLI session."""
        self.session_id = session_id
        self.storage = storage or create_memory_storage(db_path)
        self._last_injected_context: str | None = None

    def save_checkpoint(
        self,
        *,
        database_connection: dict[str, Any] | None = None,
        last_queries: list[dict[str, Any]] | None = None,
        user_preferences: dict[str, Any] | None = None,
    ) -> None:
        """Persist the current session checkpoint."""
        checkpoint = SessionCheckpoint(
            session_id=self.session_id,
            timestamp=self._now(),
            database_connection=database_connection,
            last_queries=last_queries or [],
            user_preferences=user_preferences or {},
        )
        self.storage.save_checkpoint(checkpoint)
        logger.debug("Saved memory checkpoint for session {session_id}", session_id=self.session_id)

    def save_current_context(self, query_history: Any | None = None) -> None:
        """Persist a checkpoint using the active database service and query history."""
        from database.service import get_service

        db_service = get_service()
        connection_info = None
        if db_service and db_service.is_connected():
            connection_info = db_service.get_connection_info()

        last_queries: list[dict[str, Any]] = []
        if query_history is not None:
            try:
                last_queries = [entry.to_dict() for entry in query_history.get_recent_queries(5)]
            except Exception as exc:
                logger.debug("Failed to collect query history for memory checkpoint: {error}", error=exc)

        self.save_checkpoint(
            database_connection=connection_info,
            last_queries=last_queries,
            user_preferences=self._infer_preferences(last_queries),
        )

    def remember(self, key: str, value: str, memory_type: str = "context") -> None:
        """Persist a conversation memory item."""
        if memory_type not in {"preference", "context", "fact"}:
            memory_type = "context"
        record = ConversationMemoryRecord(
            session_id=self.session_id,
            timestamp=self._now(),
            key=key.strip(),
            value=value.strip(),
            type=memory_type,  # type: ignore[arg-type]
        )
        if not record.key or not record.value:
            return
        self.storage.save_conversation_memory(record)

    def build_context(self, current_database: str | None = None, limit: int = 5) -> str:
        """Build a compact memory context relevant to the current session."""
        parts: list[str] = []

        checkpoint = self.storage.get_latest_checkpoint()
        if checkpoint:
            lines = ["Previous session:"]
            if checkpoint.database_connection:
                db_info = checkpoint.database_connection
                engine = db_info.get("engine")
                database = db_info.get("database")
                host = db_info.get("host")
                if engine:
                    lines.append(f"- Engine: {engine}")
                if database:
                    lines.append(f"- Database: {database}")
                if host:
                    lines.append(f"- Host: {host}")
            if checkpoint.last_queries:
                lines.append("- Recent SQL:")
                for query in checkpoint.last_queries[-limit:]:
                    sql = str(query.get("sql", "")).strip()
                    status = str(query.get("status", "unknown"))
                    if sql:
                        lines.append(f"  - [{status}] {self._shorten(sql)}")
            parts.append("\n".join(lines))

        recent_queries = self.storage.get_recent_queries(limit=limit, database_name=current_database)
        if recent_queries:
            lines = ["Relevant persisted SQL history:"]
            for query in recent_queries[-limit:]:
                lines.append(f"- [{query.status}] {self._shorten(query.sql)}")
            parts.append("\n".join(lines))

        context = "\n\n".join(parts).strip()
        if context == self._last_injected_context:
            return ""
        self._last_injected_context = context
        return context

    def search(self, pattern: str, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
        """Search SQL history and conversation memory."""
        queries = [record.to_dict() for record in self.storage.search_queries(pattern, limit)]
        conversations = [record.to_dict() for record in self.storage.search_conversation_memory(pattern, limit)]
        return {
            "query_history": queries,
            "conversation_memory": conversations,
        }

    def clear_all(self) -> None:
        """Clear all persistent memory."""
        self.storage.clear_all()
        self._last_injected_context = None

    def clear_history(self) -> None:
        """Clear persistent query history only."""
        self.storage.clear_queries()
        self._last_injected_context = None

    def status(self) -> MemoryStatus:
        """Return persistent memory status."""
        return self.storage.status()

    def export(self) -> dict[str, Any]:
        """Export all persistent memory."""
        return self.storage.export()

    @staticmethod
    def _infer_preferences(last_queries: list[dict[str, Any]]) -> dict[str, Any]:
        """Infer lightweight user preferences from recent query history."""
        successful = [query for query in last_queries if query.get("status") == "success"]
        return {
            "recent_successful_query_count": len(successful),
        }

    @staticmethod
    def _shorten(sql: str, max_length: int = 240) -> str:
        """Trim SQL for prompt injection."""
        normalized = " ".join(sql.split())
        if len(normalized) <= max_length:
            return normalized
        return f"{normalized[: max_length - 3]}..."

    @staticmethod
    def _now() -> str:
        """Return a local timestamp for persisted memory records."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
