from __future__ import annotations

from typing import Any, Protocol

from deerflow.knowledge.jobs.models import KnowledgeJob, KnowledgeJobType
from deerflow.knowledge.runtime.context import TrustedKnowledgeContext
from deerflow.knowledge.runtime.provider import KnowledgeServiceProvider


class KnowledgeJobHandler(Protocol):
    async def __call__(self, context: TrustedKnowledgeContext, job: KnowledgeJob) -> dict[str, Any]: ...


def provider_handlers(provider: KnowledgeServiceProvider) -> dict[KnowledgeJobType, KnowledgeJobHandler]:
    async def ingest(context: TrustedKnowledgeContext, job: KnowledgeJob) -> dict[str, Any]:
        return await provider.ingest(context, job.payload)

    async def analyze(context: TrustedKnowledgeContext, job: KnowledgeJob) -> dict[str, Any]:
        return await provider.analyze(context, job.payload)

    async def workflow_advance(context: TrustedKnowledgeContext, job: KnowledgeJob) -> dict[str, Any]:
        workflow_run_id = str(job.payload["workflow_run_id"])
        return await provider.workflow_advance(context, workflow_run_id)

    return {
        KnowledgeJobType.INGEST: ingest,
        KnowledgeJobType.ANALYZE: analyze,
        KnowledgeJobType.WORKFLOW_ADVANCE: workflow_advance,
    }
