"""Alembic environment for DeerFlow application tables.

ONLY manages DeerFlow's tables (runs, threads_meta, cron_jobs, users).
LangGraph's checkpointer tables are managed by LangGraph itself -- they
have their own schema lifecycle and must not be touched by Alembic.
"""

from __future__ import annotations

import asyncio
import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.base import Base

# Import all models so metadata is populated.
try:
    import deerflow.persistence.models as models  # register ORM models with Base.metadata

    _ = models
except ImportError:
    # Models not available — migration will work with existing metadata only.
    logging.getLogger(__name__).warning("Could not import deerflow.persistence.models; Alembic may not detect all tables")

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _async_sqlalchemy_url(raw_url: str) -> str:
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.drivername == "postgresql+asyncpg":
        return raw_url
    raise ValueError("Migration database URL must use PostgreSQL or PostgreSQL+asyncpg")


def _env_database_url() -> str | None:
    raw_url = os.environ.get("KNOWLEDGE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if raw_url:
        return _async_sqlalchemy_url(raw_url)
    return None


def _configured_database_url() -> str:
    env_url = _env_database_url()
    if env_url:
        return env_url
    raw_url = config.get_main_option("sqlalchemy.url")
    if raw_url is None:
        raise RuntimeError("sqlalchemy.url is not configured")
    return raw_url


def run_migrations_offline() -> None:
    url = _configured_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(_configured_database_url())
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
