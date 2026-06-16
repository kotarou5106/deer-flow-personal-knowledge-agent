from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.engine import make_url

from deerflow.knowledge.errors import KnowledgeDatabaseNotConfiguredError


class KnowledgeDatabaseConfig(BaseModel):
    """Explicit Knowledge database configuration.

    This config is separate from DeerFlow's runtime DatabaseConfig so ordinary
    Gateway startup does not require the Knowledge database to exist.
    """

    model_config = ConfigDict(frozen=True)

    database_url: SecretStr | None = Field(default=None, repr=False)
    echo: bool = False
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout: float = Field(default=30.0, gt=0)
    pool_recycle: int = Field(default=1800, ge=0)
    statement_timeout_ms: int | None = Field(default=None, ge=0)

    @field_validator("database_url")
    @classmethod
    def _validate_postgres_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        url = make_url(value.get_secret_value())
        if url.drivername not in {"postgresql", "postgresql+asyncpg"}:
            raise ValueError("Knowledge database URL must use PostgreSQL")
        if not url.database:
            raise ValueError("Knowledge database URL must include a database name")
        return value

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url is None:
            raise KnowledgeDatabaseNotConfiguredError("Knowledge database URL is not configured")
        raw = self.database_url.get_secret_value()
        if raw.startswith("postgresql://"):
            return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
        return raw

    @property
    def safe_url(self) -> str | None:
        if self.database_url is None:
            return None
        return str(make_url(self.database_url.get_secret_value()).render_as_string(hide_password=True))
