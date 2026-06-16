from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.extraction.schemas import ExtractedEntity
from deerflow.knowledge.models import Entity, EntityAlias


def normalize_entity_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.casefold()


def entity_types_compatible(existing: str | None, candidate: str | None) -> bool:
    if not existing or not candidate:
        return True
    return normalize_entity_key(existing) == normalize_entity_key(candidate)


@dataclass
class ResolvedEntity:
    local_id: str
    entity: Entity
    created: bool


class EntityResolver:
    async def resolve(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        extracted_entities: list[ExtractedEntity],
    ) -> dict[str, ResolvedEntity]:
        by_local_id: dict[str, ExtractedEntity] = {}
        for candidate in extracted_entities:
            if candidate.local_id not in by_local_id:
                by_local_id[candidate.local_id] = candidate

        resolved: dict[str, ResolvedEntity] = {}
        in_result_by_key: dict[tuple[str, str], Entity] = {}
        for candidate in by_local_id.values():
            key = (normalize_entity_key(candidate.canonical_name), normalize_entity_key(candidate.entity_type))
            existing = await self._find_existing(session, workspace_id, candidate)
            if existing is None:
                existing = in_result_by_key.get(key)
            if existing is None:
                existing = Entity(
                    workspace_id=workspace_id,
                    canonical_name=candidate.canonical_name,
                    entity_type=candidate.entity_type,
                    description=candidate.description,
                    metadata_json={"confidence": candidate.confidence, "extractor": "structured_knowledge_extraction"},
                )
                session.add(existing)
                await session.flush()
                in_result_by_key[key] = existing
                created = True
            else:
                created = False
                if not existing.description and candidate.description:
                    existing.description = candidate.description
            await self._add_aliases(session, workspace_id, existing, [candidate.canonical_name, *candidate.aliases])
            resolved[candidate.local_id] = ResolvedEntity(candidate.local_id, existing, created)
        return resolved

    async def _find_existing(self, session: AsyncSession, workspace_id: UUID, candidate: ExtractedEntity) -> Entity | None:
        names = [candidate.canonical_name, *candidate.aliases]
        normalized_names = {normalize_entity_key(name) for name in names if name.strip()}
        rows = (
            await session.execute(
                select(Entity).where(
                    Entity.workspace_id == workspace_id,
                )
            )
        ).scalars()
        for entity in rows:
            if not entity_types_compatible(entity.entity_type, candidate.entity_type):
                continue
            if normalize_entity_key(entity.canonical_name) in normalized_names:
                return entity
        aliases = (await session.execute(select(EntityAlias, Entity).join(Entity, (EntityAlias.entity_id == Entity.id) & (EntityAlias.workspace_id == Entity.workspace_id)).where(EntityAlias.workspace_id == workspace_id))).all()
        for alias, entity in aliases:
            if not entity_types_compatible(entity.entity_type, candidate.entity_type):
                continue
            if normalize_entity_key(alias.alias) in normalized_names:
                return entity
        return None

    async def _add_aliases(self, session: AsyncSession, workspace_id: UUID, entity: Entity, aliases: list[str]) -> None:
        existing_aliases = {normalize_entity_key(row.alias) for row in (await session.execute(select(EntityAlias).where(EntityAlias.workspace_id == workspace_id, EntityAlias.entity_id == entity.id))).scalars()}
        for alias in aliases:
            clean = alias.strip()
            if not clean:
                continue
            key = normalize_entity_key(clean)
            if key in existing_aliases:
                continue
            session.add(EntityAlias(entity_id=entity.id, workspace_id=workspace_id, alias=clean))
            existing_aliases.add(key)
        await session.flush()
