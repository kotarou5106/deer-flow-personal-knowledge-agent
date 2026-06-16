from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from deerflow.knowledge.models import AuditLog, Source
from deerflow.knowledge.repositories import AuditLogRepository, SourceRepository
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)


def _where_sql(stmt) -> str:
    return str(stmt.whereclause.compile(compile_kwargs={"literal_binds": False}))


@pytest.mark.asyncio
async def test_source_repository_scopes_reads_by_workspace() -> None:
    workspace_id = uuid4()
    source = Source(workspace_id=workspace_id, source_type="url", canonical_uri="https://example.com")
    session = SimpleNamespace(execute=AsyncMock(return_value=FakeResult([source])), add=Mock(), flush=AsyncMock())

    repo = SourceRepository(session)
    result = await repo.get_by_canonical_identity(workspace_id, "url", "https://example.com")

    assert result is source
    stmt = session.execute.await_args.args[0]
    assert "knowledge_sources.workspace_id = :workspace_id_1" in _where_sql(stmt)
    assert "knowledge_sources.source_type = :source_type_1" in _where_sql(stmt)


@pytest.mark.asyncio
async def test_repository_add_flushes_without_commit() -> None:
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    repo = SourceRepository(session)
    source = Source(workspace_id=uuid4(), source_type="url", canonical_uri="https://example.com")

    await repo.add(source)

    session.add.assert_called_once_with(source)
    session.flush.assert_awaited_once()
    assert not hasattr(session, "commit")


def test_audit_log_repository_is_append_only() -> None:
    repo = AuditLogRepository(Mock())
    public = {name for name in dir(repo) if not name.startswith("_")}

    assert {"add", "get_by_id", "list_for_workspace"} <= public
    assert "update" not in public
    assert "delete" not in public


@pytest.mark.asyncio
async def test_unit_of_work_commits_rolls_back_and_closes() -> None:
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), close=AsyncMock())
    factory = Mock(return_value=session)

    async with KnowledgeUnitOfWork(factory) as uow:
        assert uow.sources.session is session
        assert uow.audit_logs.session is session
        await uow.commit()

    session.commit.assert_awaited_once()
    session.rollback.assert_not_called()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_on_exception() -> None:
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), close=AsyncMock())
    factory = Mock(return_value=session)

    with pytest.raises(RuntimeError, match="boom"):
        async with KnowledgeUnitOfWork(factory):
            raise RuntimeError("boom")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_called()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_log_add_flushes_append_only_row() -> None:
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    row = AuditLog(workspace_id=uuid4(), event_type="created", target_type="source", target_id="source-1")

    await AuditLogRepository(session).add(row)

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
