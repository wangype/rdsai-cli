"""Typed records used by persistent memory storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


MemoryType = Literal["preference", "context", "fact"]


@dataclass(slots=True, kw_only=True)
class QueryMemoryRecord:
    """A persisted SQL query history record."""

    id: int | None = None
    timestamp: str
    sql: str
    status: str
    execution_time: float | None = None
    affected_rows: int | None = None
    error_message: str | None = None
    database_name: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the query memory record to a JSON-serializable dictionary."""
        return asdict(self)


@dataclass(slots=True, kw_only=True)
class SessionCheckpoint:
    """A persisted session checkpoint."""

    session_id: str
    timestamp: str
    database_connection: dict[str, Any] | None = None
    last_queries: list[dict[str, Any]] = field(default_factory=list)
    user_preferences: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the checkpoint to a JSON-serializable dictionary."""
        return asdict(self)


@dataclass(slots=True, kw_only=True)
class ConversationMemoryRecord:
    """A persisted conversation memory item."""

    id: int | None = None
    session_id: str
    timestamp: str
    key: str
    value: str
    type: MemoryType

    def to_dict(self) -> dict[str, Any]:
        """Convert the conversation memory item to a JSON-serializable dictionary."""
        return asdict(self)


@dataclass(slots=True, kw_only=True)
class MemoryStatus:
    """Summary information about persistent memory."""

    available: bool
    database_path: str
    query_count: int = 0
    checkpoint_count: int = 0
    conversation_count: int = 0
    latest_session_id: str | None = None
    latest_session_timestamp: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert memory status to a JSON-serializable dictionary."""
        return asdict(self)
