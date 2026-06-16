from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_migration_module():
    path = Path(__file__).resolve().parents[2] / "packages" / "harness" / "deerflow" / "persistence" / "migrations" / "versions" / "20260616_0001_knowledge_persistence.py"
    spec = importlib.util.spec_from_file_location("knowledge_migration_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_enables_pgvector_without_dropping_shared_extension() -> None:
    module = _load_migration_module()

    operations: list[str] = []
    module.op.execute = operations.append
    module.op.get_bind = lambda: None
    module.KnowledgeBase.metadata.create_all = lambda bind: operations.append("create_all")
    module.KnowledgeBase.metadata.drop_all = lambda bind: operations.append("drop_all")

    module.upgrade()
    module.downgrade()

    assert "CREATE EXTENSION IF NOT EXISTS vector" in operations
    assert "create_all" in operations
    assert "drop_all" in operations
    assert not any("DROP EXTENSION" in op for op in operations)
