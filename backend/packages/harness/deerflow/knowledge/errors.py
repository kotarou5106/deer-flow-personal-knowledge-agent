from __future__ import annotations


class KnowledgePersistenceError(Exception):
    """Base class for Knowledge persistence errors."""


class KnowledgeDatabaseNotConfiguredError(KnowledgePersistenceError):
    """Raised when a database operation is requested without a database URL."""


class KnowledgeDatabaseNotInitializedError(KnowledgePersistenceError):
    """Raised when a database session is requested before initialization."""


class WorkspaceIsolationError(KnowledgePersistenceError):
    """Raised when a repository operation would cross workspace boundaries."""
