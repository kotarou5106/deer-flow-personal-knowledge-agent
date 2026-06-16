from __future__ import annotations

from uuid import UUID

from deerflow.knowledge.models import Chunk, DocumentRevision, Source
from deerflow.knowledge.retrieval.context_builder import build_context_pack
from deerflow.knowledge.retrieval.fusion import reciprocal_rank_fusion
from deerflow.knowledge.retrieval.graph import GraphRetriever
from deerflow.knowledge.retrieval.indexing import EmbeddingModel
from deerflow.knowledge.retrieval.lexical import LexicalRetriever
from deerflow.knowledge.retrieval.parent_expansion import expand_parent_context
from deerflow.knowledge.retrieval.query_analyzer import QueryAnalyzer
from deerflow.knowledge.retrieval.reranker import Reranker, RerankerModel
from deerflow.knowledge.retrieval.schemas import CandidateType, EvidenceContextPack, Provenance, RetrievalCandidate, RetrievalChannel, RRFConfig
from deerflow.knowledge.retrieval.vector import VectorRetriever
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory


class RetrievalService:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        embedding_model: EmbeddingModel | None = None,
        query_analyzer: QueryAnalyzer | None = None,
        reranker_model: RerankerModel | None = None,
        rrf_config: RRFConfig | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._query_analyzer = query_analyzer or QueryAnalyzer()
        self._lexical = LexicalRetriever()
        self._vector = VectorRetriever(embedding_model)
        self._graph = GraphRetriever()
        self._reranker = Reranker(model=reranker_model)
        self._rrf_config = rrf_config or RRFConfig()

    async def retrieve(
        self,
        *,
        workspace_id: UUID,
        query: str,
        filters: dict | None = None,
        context_budget: int = 8000,
    ) -> EvidenceContextPack:
        query_spec = await self._query_analyzer.analyze(query, **(filters or {}))
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            candidates = [
                *await self._lexical.retrieve(uow.session, workspace_id=workspace_id, query_spec=query_spec),
                *await self._vector.retrieve(uow.session, workspace_id=workspace_id, query_spec=query_spec),
                *await self._graph.retrieve(uow.session, workspace_id=workspace_id, query_spec=query_spec),
            ]
        fused = reciprocal_rank_fusion(candidates, self._rrf_config)
        expanded = await expand_parent_context(fused, load_parent=self._load_parent_candidate, context_budget=context_budget)
        reranked, warnings = await self._reranker.rerank(query_spec.query_text, expanded)
        return build_context_pack(query_spec=query_spec, candidates=reranked, context_budget=context_budget, warnings=warnings)

    async def _load_parent_candidate(self, workspace_id: UUID, parent_chunk_id: UUID) -> RetrievalCandidate | None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            chunk = await uow.session.get(Chunk, parent_chunk_id)
            if chunk is None or chunk.workspace_id != workspace_id:
                return None
            revision = await uow.session.get(DocumentRevision, chunk.revision_id)
            if revision is None or revision.workspace_id != workspace_id:
                return None
            source = await uow.session.get(Source, revision.source_id)
            if source is None or source.workspace_id != workspace_id:
                return None
            return RetrievalCandidate(
                candidate_type=CandidateType.CHUNK,
                candidate_id=chunk.id,
                workspace_id=workspace_id,
                source_id=source.id,
                revision_id=revision.id,
                chunk_id=chunk.id,
                content=chunk.content,
                retrieval_channel=RetrievalChannel.LEXICAL,
                raw_score=0.0,
                rank=999999,
                metadata={"parent_context": True, "section_path": list(chunk.section_path or [])},
                provenance=Provenance(
                    source_id=source.id,
                    snapshot_id=revision.snapshot_id,
                    revision_id=revision.id,
                    chunk_id=chunk.id,
                    page_number=chunk.page_number,
                    section_path=[str(part) for part in (chunk.section_path or [])],
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                ),
            )


async def retrieve(session_factory: SessionFactory, *, workspace_id: UUID, query: str, filters: dict | None = None) -> EvidenceContextPack:
    return await RetrievalService(session_factory).retrieve(workspace_id=workspace_id, query=query, filters=filters)
