from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.errors import KnowledgeDatabaseNotConfiguredError, KnowledgeDatabaseNotInitializedError


def _json_serializer(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False)


class KnowledgeDatabase:
    """Explicit async engine/session lifecycle for Knowledge persistence."""

    def __init__(
        self,
        config: KnowledgeDatabaseConfig,
        *,
        engine: AsyncEngine | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._config = config
        self._engine = engine
        self._session_factory = session_factory

    @property
    def engine(self) -> AsyncEngine | None:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession] | None:
        return self._session_factory

    async def initialize(self) -> None:
        if self._session_factory is not None:
            return
        try:
            url = self._config.sqlalchemy_url
        except KnowledgeDatabaseNotConfiguredError:
            raise

        connect_args: dict[str, object] = {}
        if self._config.statement_timeout_ms is not None:
            connect_args["server_settings"] = {"statement_timeout": str(self._config.statement_timeout_ms)}

        self._engine = create_async_engine(
            url,
            echo=self._config.echo,
            pool_size=self._config.pool_size,
            max_overflow=self._config.max_overflow,
            pool_timeout=self._config.pool_timeout,
            pool_recycle=self._config.pool_recycle,
            pool_pre_ping=True,
            connect_args=connect_args,
            json_serializer=_json_serializer,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._session_factory is None:
            raise KnowledgeDatabaseNotInitializedError("Knowledge database is not initialized")
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._session_factory = None
