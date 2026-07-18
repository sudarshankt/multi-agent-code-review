from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from eval.report.aggregate_results import write_report_files
from eval.runners.run_ablation_eval import run_ablation_eval
from eval.runners.run_bug_eval import run_bug_eval
from eval.runners.run_patch_eval import run_patch_eval
from eval.runners.run_project_agent_eval import run_project_agent_eval
from eval.runners.run_rag_eval import run_rag_eval
from eval.runners.run_security_eval import run_security_eval
from eval.runners.run_style_eval import run_style_eval


def run_all_evals(output_dir: str | Path | None = None) -> tuple[dict, Path, Path]:
    """Execute the evaluation runners and aggregate their outputs into report files."""
    output_path = Path(output_dir or "results")
    output_path.mkdir(parents=True, exist_ok=True)

    results = [
        run_security_eval(output_path),
        run_bug_eval(output_path),
        run_patch_eval(output_path),
        run_style_eval(output_path),
        run_rag_eval(output_path),
        run_ablation_eval(output_path),
    ]

    sample_review = Path("eval/datasets/sample_review.json")
    if sample_review.exists():
        results.append(run_project_agent_eval(sample_review, output_path))

    report = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "count": len(results),
            "agents": sorted({item.get("agent", "unknown") for item in results}),
        },
        "results": results,
    }

    json_path, markdown_path = write_report_files(report, output_path)
    return report, json_path, markdown_path


if __name__ == "__main__":
    run_all_evals()
