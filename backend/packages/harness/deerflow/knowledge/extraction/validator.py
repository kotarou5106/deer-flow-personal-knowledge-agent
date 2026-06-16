from __future__ import annotations

from collections import Counter
from copy import deepcopy
from uuid import UUID

from deerflow.knowledge.extraction.schemas import (
    ChunkText,
    ExtractedClaim,
    ExtractedEvidenceSpan,
    ExtractedRelation,
    StructuredExtractionOutput,
    ValidatedExtraction,
    ValidationIssue,
    ValidationSeverity,
)


class ExtractionValidator:
    def validate(self, output: StructuredExtractionOutput, chunks: list[ChunkText], workspace_id: UUID) -> ValidatedExtraction:
        chunk_map = {chunk.id: chunk for chunk in chunks}
        issues: list[ValidationIssue] = []
        sanitized = deepcopy(output)
        entity_ids = {entity.local_id for entity in sanitized.entities}
        if len(entity_ids) != len(sanitized.entities):
            duplicate_ids = [local_id for local_id, count in Counter(entity.local_id for entity in sanitized.entities).items() if count > 1]
            issues.append(
                ValidationIssue(
                    path="entities",
                    error_type="duplicate_local_id",
                    message=f"Duplicate entity local IDs: {', '.join(sorted(duplicate_ids))}",
                    severity=ValidationSeverity.REJECTED,
                )
            )
            sanitized.entities = _dedupe_entities(sanitized.entities)
            entity_ids = {entity.local_id for entity in sanitized.entities}

        valid_claims: list[ExtractedClaim] = []
        for index, claim in enumerate(sanitized.claims):
            item_issues = self._validate_claim(claim, index, entity_ids, chunk_map, workspace_id)
            issues.extend(item_issues)
            if not any(issue.severity == ValidationSeverity.REJECTED for issue in item_issues):
                valid_claims.append(claim)

        valid_relations: list[ExtractedRelation] = []
        seen_relations: set[tuple[str, str, str, tuple[tuple[UUID, int, int], ...]]] = set()
        for index, relation in enumerate(sanitized.relations):
            item_issues = self._validate_relation(relation, index, entity_ids, chunk_map, workspace_id)
            evidence_key = tuple((span.chunk_id, span.start_offset, span.end_offset) for span in relation.evidence_spans)
            relation_key = (relation.source_entity_local_id, relation.relation_type, relation.target_entity_local_id, evidence_key)
            if relation_key in seen_relations:
                item_issues.append(
                    ValidationIssue(
                        path=f"relations[{index}]",
                        error_type="duplicate_relation",
                        message="Duplicate relation in the same extraction output",
                        severity=ValidationSeverity.REJECTED,
                    )
                )
            seen_relations.add(relation_key)
            issues.extend(item_issues)
            if not any(issue.severity == ValidationSeverity.REJECTED for issue in item_issues):
                valid_relations.append(relation)

        rejected = (len(sanitized.claims) - len(valid_claims)) + (len(sanitized.relations) - len(valid_relations))
        sanitized.claims = valid_claims
        sanitized.relations = valid_relations
        return ValidatedExtraction(output=sanitized, issues=issues, rejected_item_count=rejected)

    def _validate_claim(
        self,
        claim: ExtractedClaim,
        index: int,
        entity_ids: set[str],
        chunk_map: dict[UUID, ChunkText],
        workspace_id: UUID,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if claim.subject_entity_local_id not in entity_ids:
            issues.append(_rejected(f"claims[{index}].subject_entity_local_id", "unknown_local_id", "Claim subject does not reference an extracted entity"))
        if claim.object_entity_local_id and claim.object_entity_local_id not in entity_ids:
            issues.append(_rejected(f"claims[{index}].object_entity_local_id", "unknown_local_id", "Claim object entity does not reference an extracted entity"))
        if not claim.claim_text.strip():
            issues.append(_rejected(f"claims[{index}].claim_text", "blank_claim", "Claim text must not be blank"))
        issues.extend(_validate_evidence_spans(claim.evidence_spans, f"claims[{index}].evidence_spans", chunk_map, workspace_id))
        return issues

    def _validate_relation(
        self,
        relation: ExtractedRelation,
        index: int,
        entity_ids: set[str],
        chunk_map: dict[UUID, ChunkText],
        workspace_id: UUID,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if relation.source_entity_local_id not in entity_ids:
            issues.append(_rejected(f"relations[{index}].source_entity_local_id", "unknown_local_id", "Relation source does not reference an extracted entity"))
        if relation.target_entity_local_id not in entity_ids:
            issues.append(_rejected(f"relations[{index}].target_entity_local_id", "unknown_local_id", "Relation target does not reference an extracted entity"))
        if not relation.relation_type.strip():
            issues.append(_rejected(f"relations[{index}].relation_type", "blank_relation_type", "Relation type must not be blank"))
        issues.extend(_validate_evidence_spans(relation.evidence_spans, f"relations[{index}].evidence_spans", chunk_map, workspace_id))
        return issues


def _validate_evidence_spans(
    spans: list[ExtractedEvidenceSpan],
    path: str,
    chunk_map: dict[UUID, ChunkText],
    workspace_id: UUID,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, span in enumerate(spans):
        chunk = chunk_map.get(span.chunk_id)
        span_path = f"{path}[{index}]"
        if chunk is None:
            issues.append(_rejected(f"{span_path}.chunk_id", "unknown_chunk", "Evidence references a chunk outside the selected revision"))
            continue
        if chunk.workspace_id != workspace_id:
            issues.append(_rejected(f"{span_path}.chunk_id", "workspace_mismatch", "Evidence chunk belongs to a different workspace"))
            continue
        if span.end_offset > len(chunk.content):
            issues.append(_rejected(span_path, "offset_out_of_range", "Evidence offsets exceed chunk length"))
            continue
        if chunk.content[span.start_offset : span.end_offset] == span.quoted_text:
            continue
        matches = _find_all(chunk.content, span.quoted_text)
        if len(matches) == 1:
            start = matches[0]
            span.start_offset = start
            span.end_offset = start + len(span.quoted_text)
            issues.append(
                ValidationIssue(
                    path=span_path,
                    error_type="offset_corrected",
                    message="Evidence offsets were corrected using a unique exact quote match in the same chunk",
                    fix_hint="Use corrected Python slice offsets next time",
                    severity=ValidationSeverity.FIXED,
                )
            )
            continue
        issues.append(
            _rejected(
                span_path,
                "quote_mismatch",
                "Evidence quote does not match the provided offsets and cannot be uniquely located",
                "Return exact quoted_text and offsets from the current chunk",
            )
        )
    return issues


def _find_all(content: str, needle: str) -> list[int]:
    if not needle:
        return []
    positions: list[int] = []
    start = 0
    while True:
        index = content.find(needle, start)
        if index == -1:
            return positions
        positions.append(index)
        start = index + 1


def _dedupe_entities(entities):
    seen: set[str] = set()
    unique = []
    for entity in entities:
        if entity.local_id in seen:
            continue
        seen.add(entity.local_id)
        unique.append(entity)
    return unique


def _rejected(path: str, error_type: str, message: str, fix_hint: str | None = None) -> ValidationIssue:
    return ValidationIssue(path=path, error_type=error_type, message=message, fix_hint=fix_hint, severity=ValidationSeverity.REJECTED)
