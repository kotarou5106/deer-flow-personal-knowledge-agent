from __future__ import annotations

from pathlib import Path

from deerflow.knowledge.evaluation import load_dataset, run_evaluation, write_reports


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dataset = load_dataset(repo_root / "backend/tests/fixtures/knowledge/evaluation_dataset.json")
    output = run_evaluation(dataset)
    write_reports(
        output,
        repo_root / "artifacts/personal-knowledge-agent-evaluation.json",
        repo_root / "artifacts/personal-knowledge-agent-evaluation.md",
    )


if __name__ == "__main__":
    main()
