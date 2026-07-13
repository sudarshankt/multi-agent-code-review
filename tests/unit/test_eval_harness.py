from __future__ import annotations

from eval.metrics.classification import calculate_binary_metrics, bootstrap_confidence_interval
from eval.metrics.from_project_outputs import summarize_findings
from eval.report.aggregate_results import build_report_payload, render_markdown_report
from src.models.finding import FixResult
from src.models.review import PRInfo, Review
from src.services.artifact_service import persist_generated_artifacts


def test_calculate_binary_metrics_returns_expected_values() -> None:
    metrics = calculate_binary_metrics([1, 0, 1, 1], [1, 0, 0, 1])

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 2 / 3
    assert metrics["f1"] == 0.8


def test_bootstrap_confidence_interval_is_bounded() -> None:
    ci = bootstrap_confidence_interval([1, 0, 1, 1, 0, 0], n_bootstrap=50)

    assert len(ci) == 2
    assert ci[0] <= ci[1]
    assert 0.0 <= ci[0] <= 1.0
    assert 0.0 <= ci[1] <= 1.0


def test_aggregate_report_renders_markdown_table() -> None:
    results = [
        {
            "benchmark": "PrimeVul",
            "agent": "security",
            "metrics": {"precision": 0.8, "recall": 0.7, "f1": 0.75},
            "baseline_zero_shot": {"f1": 0.6},
        },
        {
            "benchmark": "Defects4J",
            "agent": "bug_detection",
            "metrics": {"precision": 0.9, "recall": 0.8, "f1": 0.85},
            "baseline_zero_shot": {"f1": 0.7},
        },
    ]

    report = build_report_payload(results)
    markdown = render_markdown_report(report)

    assert report["summary"]["count"] == 2
    assert "| Benchmark | Agent | F1 |" in markdown
    assert "PrimeVul" in markdown


def test_summarize_findings_preserves_agent_inputs() -> None:
    review = Review(
        pr_info=PRInfo(owner="octo", repo="demo", pr_number=1),
        agent_inputs={
            "security": {
                "files": {"app.py": "print('hi')"},
                "context": {"files_bypassed": 0},
            },
            "bug_detection": {
                "files": {"app.py": "print('hi')"},
                "context": {"files_bypassed": 1},
            },
        },
    )

    summary = summarize_findings(review)

    assert summary["input_agent_count"] == 2
    assert summary["input_file_count"] == 2
    assert summary["input_files_bypassed"] == 1


def test_persist_generated_artifacts_writes_reviewable_code(tmp_path: object) -> None:
    result = FixResult(
        category="security",
        file_path="src/app.py",
        success=True,
        fixed_code="print('safe')\n",
        commit_sha="abc123",
        commit_message="fix security",
    )

    manifest = persist_generated_artifacts("review-1", [result], output_dir=tmp_path)

    artifact_path = tmp_path / "review-1" / "src" / "app.py"
    assert artifact_path.exists()
    assert artifact_path.read_text(encoding="utf-8") == "print('safe')\n"
    assert manifest[0]["artifact_path"].endswith("review-1/src/app.py")
    assert result.artifact_path == manifest[0]["artifact_path"]
