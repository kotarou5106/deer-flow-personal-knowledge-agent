from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class WorkspaceRepository[T]:
    """Internal helper for typed repositories.

    Public callers use concrete repositories; this class only centralizes the
    workspace filter mechanics so every query gets the same isolation guard.
    """

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _workspace_stmt(self, workspace_id: UUID) -> Select[tuple[T]]:
        return select(self.model).where(self.model.workspace_id == workspace_id)  # type: ignore[attr-defined]

    async def _first(self, stmt: Select[tuple[T]]) -> T | None:
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _all(self, stmt: Select[tuple[T]]) -> list[T]:
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, workspace_id: UUID, object_id: UUID) -> T | None:
        stmt = self._workspace_stmt(workspace_id).where(self.model.id == object_id)  # type: ignore[attr-defined]
        return await self._first(stmt)

    async def list_for_workspace(self, workspace_id: UUID, *, limit: int = 100, offset: int = 0) -> list[T]:
        stmt = self._workspace_stmt(workspace_id).limit(limit).offset(offset)
        return await self._all(stmt)

    async def add(self, row: T) -> T:
        self.session.add(row)
        await self.session.flush()
        return row
