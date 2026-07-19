from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from eval.config_runtime import load_eval_config
from eval.optional_dependencies import collect_optional_dependency_status
from eval.report.aggregate_results import write_report_files
from eval.report.render_results import write_html_report
from eval.runners.run_ablation_eval import run_ablation_eval
from eval.runners.run_bug_eval import run_bug_eval
from eval.runners.run_patch_eval import run_patch_eval
from eval.runners.run_performance_eval import run_performance_eval
from eval.runners.run_project_agent_eval import run_project_agent_eval
from eval.runners.run_rag_eval import run_rag_eval
from eval.runners.run_security_eval import run_security_eval
from eval.runners.run_style_eval import run_style_eval


def run_all_evals(output_dir: str | Path | None = None) -> tuple[dict, Path, Path]:
    """Execute the evaluation runners and aggregate their outputs into report files."""
    cfg = load_eval_config()
    output_path = Path(output_dir or cfg.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = [
        run_security_eval(output_path),
        run_bug_eval(output_path),
        run_patch_eval(output_path),
        run_style_eval(output_path),
        run_performance_eval(output_path),
        run_rag_eval(output_path),
    ]

    results.append(run_ablation_eval(output_path, reference_results=results))

    sample_review = Path("eval/datasets/sample_review.json")
    if sample_review.exists():
        results.append(run_project_agent_eval(sample_review, output_path))

    report = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "count": len(results),
            "agents": sorted({item.get("agent", "unknown") for item in results}),
        },
        "optional_dependencies": collect_optional_dependency_status(),
        "results": results,
    }

    json_path, markdown_path = write_report_files(report, output_path)
    write_html_report(json_path, output_path / "evaluation_results.html")
    return report, json_path, markdown_path


if __name__ == "__main__":
    run_all_evals()
