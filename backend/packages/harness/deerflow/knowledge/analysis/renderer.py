from __future__ import annotations

from deerflow.knowledge.analysis.schemas import AnalysisResult, EvidenceCitation


def render_markdown(result: AnalysisResult) -> str:
    lines = [
        "# Analysis",
        "",
        result.answer,
        "",
        "## Supported Facts",
    ]
    if result.supported_facts:
        for fact in result.supported_facts:
            markers = " ".join(f"[{citation.citation_id}]" for citation in fact.citations)
            lines.append(f"- {fact.statement} {markers}")
    else:
        lines.append("- No supported facts were established from the retrieved evidence.")

    lines.extend(["", "## Inferred Conclusions"])
    if result.inferred_conclusions:
        for conclusion in result.inferred_conclusions:
            markers = " ".join(f"[{citation.citation_id}]" for citation in conclusion.based_on_citations)
            suffix = f" {markers}" if markers else ""
            lines.append(f"- Inference: {conclusion.statement}{suffix}")
            lines.append(f"  Reasoning: {conclusion.reasoning_summary}")
    else:
        lines.append("- No inferred conclusions were generated.")

    lines.extend(["", "## Unsupported Or Insufficient"])
    if result.unsupported_or_insufficient_claims:
        for claim in result.unsupported_or_insufficient_claims:
            lines.append(f"- {claim.statement} ({claim.severity}): {claim.reason}")
    else:
        lines.append("- No unsupported claims were reported.")

    lines.extend(["", "## Unresolved Questions"])
    if result.unresolved_questions:
        for question in result.unresolved_questions:
            lines.append(f"- {question.question}: {question.why_unresolved} Needed evidence: {question.needed_evidence}")
    else:
        lines.append("- No unresolved questions were reported.")

    lines.extend(["", "## Evidence"])
    for citation in result.evidence_used:
        lines.append(_render_citation(citation))

    lines.extend(["", "## Sources"])
    if result.source_summary:
        for source in result.source_summary:
            parts = [f"- source_id={source.source_id or ''}"]
            if source.title:
                parts.append(f"title={source.title}")
            if source.uri:
                parts.append(f"uri={source.uri}")
            if source.revision_id:
                parts.append(f"revision_id={source.revision_id}")
            lines.append("; ".join(parts))
    else:
        lines.append("- No sources were used.")

    if result.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines).strip() + "\n"


def _render_citation(citation: EvidenceCitation) -> str:
    quote = citation.quoted_text.strip()
    if len(quote) > 180:
        quote = quote[:180].rstrip() + "..."
    return f'- [{citation.citation_id}] source={citation.source_id or ""}; revision={citation.revision_id or ""}; chunk={citation.chunk_id or ""}; evidence_span={citation.evidence_span_id or ""}; quote="{quote}"'
