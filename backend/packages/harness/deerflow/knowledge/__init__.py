"""Personal Knowledge Agent persistence package.

The package is intentionally inert on import: callers must explicitly create a
KnowledgeDatabase or UnitOfWork factory before any database resources exist.
"""

from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase

__all__ = ["KnowledgeDatabase", "KnowledgeDatabaseConfig"]
