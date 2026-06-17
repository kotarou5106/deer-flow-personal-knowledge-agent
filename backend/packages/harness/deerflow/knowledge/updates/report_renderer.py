from __future__ import annotations

from deerflow.knowledge.updates.schemas import KnowledgeUpdateReport


def render_markdown_report(report: KnowledgeUpdateReport) -> str:
    lines = [
        "# Knowledge Update Report",
        "",
        f"- Run: `{report.run_id}`",
        f"- Source: `{report.source_id}`",
        f"- Old revision: `{report.old_revision_id}`",
        f"- New revision: `{report.new_revision_id}`",
        f"- Status: `{report.status}`",
        "",
        "## Diff",
        "",
        f"- Unchanged: {report.diff_summary.unchanged}",
        f"- Added: {report.diff_summary.added}",
        f"- Removed: {report.diff_summary.removed}",
        f"- Modified: {report.diff_summary.modified}",
        f"- Moved: {report.diff_summary.moved}",
        "",
        "## Incremental Work",
        "",
        f"- Reprocessed chunks: {len(report.reprocessed_chunks)}",
        f"- Reused chunks: {len(report.reused_chunks)}",
        f"- Superseded claims: {len(report.superseded_claims)}",
        f"- New claims: {len(report.new_claims)}",
        f"- Conflict groups: {len(report.conflict_groups)}",
        f"- Stale artifacts: {len(report.stale_artifacts)}",
    ]
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in report.errors)
    return "\n".join(lines) + "\n"
