from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from deerflow.knowledge.models import KnowledgeBase
from deerflow.knowledge.models.base import Vector

EXPECTED_TABLES = {
    "knowledge_sources",
    "knowledge_source_snapshots",
    "knowledge_document_revisions",
    "knowledge_chunks",
    "knowledge_entities",
    "knowledge_entity_aliases",
    "knowledge_claims",
    "knowledge_claim_evidence_links",
    "knowledge_evidence_spans",
    "knowledge_relations",
    "knowledge_artifacts",
    "knowledge_artifact_evidence_links",
    "knowledge_workflow_runs",
    "knowledge_workflow_artifacts",
    "knowledge_approval_requests",
    "knowledge_action_executions",
    "knowledge_collections",
    "knowledge_collection_sources",
    "knowledge_collection_entities",
    "knowledge_collection_claims",
    "knowledge_collection_artifacts",
    "knowledge_topics",
    "knowledge_ingestion_jobs",
    "knowledge_extraction_runs",
    "knowledge_indexing_runs",
    "knowledge_conflict_groups",
    "knowledge_conflict_group_claims",
    "knowledge_audit_logs",
}


def test_metadata_declares_all_authoritative_knowledge_tables() -> None:
    assert EXPECTED_TABLES <= set(KnowledgeBase.metadata.tables)


def test_user_queryable_tables_have_workspace_id() -> None:
    for name in EXPECTED_TABLES:
        table = KnowledgeBase.metadata.tables[name]
        if name == "knowledge_entity_aliases":
            # Alias rows are always reached through their workspace-scoped entity.
            continue
        assert "workspace_id" in table.c, name


def test_core_constraints_are_declared() -> None:
    sources = KnowledgeBase.metadata.tables["knowledge_sources"]
    snapshots = KnowledgeBase.metadata.tables["knowledge_source_snapshots"]
    revisions = KnowledgeBase.metadata.tables["knowledge_document_revisions"]
    chunks = KnowledgeBase.metadata.tables["knowledge_chunks"]
    actions = KnowledgeBase.metadata.tables["knowledge_action_executions"]

    assert any(isinstance(c, UniqueConstraint) and {"workspace_id", "source_type", "canonical_uri"} <= {col.name for col in c.columns} for c in sources.constraints)
    assert any(isinstance(c, UniqueConstraint) and {"source_id", "content_hash"} <= {col.name for col in c.columns} for c in snapshots.constraints)
    assert any(isinstance(c, UniqueConstraint) and {"source_id", "revision_number"} <= {col.name for col in c.columns} for c in revisions.constraints)
    assert any(isinstance(c, UniqueConstraint) and {"revision_id", "chunk_index"} <= {col.name for col in c.columns} for c in chunks.constraints)
    assert any(isinstance(c, UniqueConstraint) and {"workspace_id", "connector_type", "idempotency_key"} <= {col.name for col in c.columns} for c in actions.constraints)
    assert any(isinstance(c, CheckConstraint) and "start_offset <= end_offset" in str(c.sqltext) for c in chunks.constraints)


def test_workspace_composite_foreign_keys_exist() -> None:
    revisions = KnowledgeBase.metadata.tables["knowledge_document_revisions"]
    fks = [c for c in revisions.constraints if isinstance(c, ForeignKeyConstraint)]
    assert any({"source_id", "workspace_id"} <= {col.name for col in fk.columns} for fk in fks)
    assert any({"snapshot_id", "workspace_id"} <= {col.name for col in fk.columns} for fk in fks)


def test_postgresql_ddl_compiles_with_jsonb_uuid_and_vector() -> None:
    dialect = postgresql.dialect()
    ddl = "\n".join(str(CreateTable(table).compile(dialect=dialect)) for table in KnowledgeBase.metadata.sorted_tables)

    assert "UUID" in ddl
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "JSONB" in ddl
    assert "vector" in ddl
    assert "CHECK" in ddl


def test_vector_type_serializes_python_embeddings_for_pgvector() -> None:
    vector = Vector()

    bind = vector.bind_processor(postgresql.dialect())
    assert bind is not None
    assert bind([0.1, 2, -3.5]) == "[0.1,2.0,-3.5]"
    assert bind("[1,2,3]") == "[1,2,3]"
    assert bind(None) is None

    result = vector.result_processor(postgresql.dialect(), None)
    assert result is not None
    assert result("[0.1,2.0,-3.5]") == [0.1, 2.0, -3.5]
    assert result(None) is None
