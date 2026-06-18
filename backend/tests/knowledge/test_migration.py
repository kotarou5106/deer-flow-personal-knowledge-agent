from __future__ import annotations

import contextlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_migration_module():
    path = Path(__file__).resolve().parents[2] / "packages" / "harness" / "deerflow" / "persistence" / "migrations" / "versions" / "20260616_0001_knowledge_persistence.py"
    spec = importlib.util.spec_from_file_location("knowledge_migration_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_migration_env_module(monkeypatch, *, config_url: str = "sqlite+aiosqlite:///./data/deerflow.db"):
    path = Path(__file__).resolve().parents[2] / "packages" / "harness" / "deerflow" / "persistence" / "migrations" / "env.py"
    calls: list[object] = []
    fake_context = SimpleNamespace(
        config=SimpleNamespace(config_file_name=None, get_main_option=lambda name: config_url if name == "sqlalchemy.url" else None),
        is_offline_mode=lambda: True,
        configure=lambda **kwargs: calls.append(("configure", kwargs)),
        begin_transaction=lambda: contextlib.nullcontext(),
        run_migrations=lambda: calls.append("run_migrations"),
    )
    monkeypatch.setitem(sys.modules, "alembic", SimpleNamespace(context=fake_context))
    monkeypatch.setitem(sys.modules, "alembic.context", fake_context)

    spec = importlib.util.spec_from_file_location("knowledge_migration_env_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_migration_enables_pgvector_without_dropping_shared_extension(monkeypatch) -> None:
    module = _load_migration_module()

    operations: list[str] = []
    monkeypatch.setattr(module.op, "execute", operations.append)
    monkeypatch.setattr(module.op, "get_bind", lambda: None)
    monkeypatch.setattr(module.KnowledgeBase.metadata, "create_all", lambda bind: operations.append("create_all"))
    monkeypatch.setattr(module.KnowledgeBase.metadata, "drop_all", lambda bind: operations.append("drop_all"))

    module.upgrade()
    module.downgrade()

    assert "CREATE EXTENSION IF NOT EXISTS vector" in operations
    assert "create_all" in operations
    assert "drop_all" in operations
    assert not any("DROP EXTENSION" in op for op in operations)


def test_alembic_env_prefers_knowledge_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback:secret@postgres/fallback_db")
    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", "postgresql://knowledge:secret@postgres/knowledge_db")

    module, _calls = _load_migration_env_module(monkeypatch)

    assert module._configured_database_url() == "postgresql+asyncpg://knowledge:secret@postgres/knowledge_db"


def test_alembic_env_falls_back_to_database_url(monkeypatch) -> None:
    monkeypatch.delenv("KNOWLEDGE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback:secret@postgres/fallback_db")

    module, _calls = _load_migration_env_module(monkeypatch)

    assert module._configured_database_url() == "postgresql+asyncpg://fallback:secret@postgres/fallback_db"


def test_alembic_env_uses_ini_url_when_env_database_urls_are_missing(monkeypatch) -> None:
    monkeypatch.delenv("KNOWLEDGE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    module, _calls = _load_migration_env_module(monkeypatch, config_url="sqlite+aiosqlite:///./fallback.db")

    assert module._configured_database_url() == "sqlite+aiosqlite:///./fallback.db"


@pytest.mark.asyncio
async def test_alembic_env_passes_asyncpg_url_to_async_engine(monkeypatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", "postgresql+asyncpg://knowledge:secret@postgres/knowledge_db")
    module, _calls = _load_migration_env_module(monkeypatch)
    created_urls: list[str] = []

    class FakeConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb) -> None:
            return None

        async def run_sync(self, callback) -> None:
            callback(self)

    class FakeEngine:
        def connect(self) -> FakeConnection:
            return FakeConnection()

        async def dispose(self) -> None:
            created_urls.append("disposed")

    def create_engine(url: str) -> FakeEngine:
        created_urls.append(url)
        return FakeEngine()

    monkeypatch.setattr(module, "create_async_engine", create_engine)

    await module.run_migrations_online()

    assert created_urls == ["postgresql+asyncpg://knowledge:secret@postgres/knowledge_db", "disposed"]


def test_alembic_env_rejects_unsupported_env_database_url(monkeypatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", "mysql://user:secret@db/example")

    with pytest.raises(ValueError, match="Migration database URL must use PostgreSQL"):
        _load_migration_env_module(monkeypatch)
