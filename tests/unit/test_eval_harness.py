from __future__ import annotations

import json
from pathlib import Path

from eval.metrics.classification import (
    bootstrap_confidence_interval,
    calculate_binary_metrics,
)
from eval.metrics.from_project_outputs import summarize_findings
from eval.report.aggregate_results import build_report_payload, render_markdown_report
from eval.runners.run_performance_eval import run_performance_eval
from eval.zero_shot_baseline import _extract_prediction, run_zero_shot_binary_predictions
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
    assert "| Benchmark | Agent | Metric | Value | Baseline |" in markdown
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

    assert summary["agents"] == ["security", "bug_detection"]
    assert summary["input_agent_count"] == 2
    assert summary["input_file_count"] == 2
    assert summary["input_files_bypassed"] == 1


def test_zero_shot_predictions_are_cached(tmp_path: Path) -> None:
    rows = [{"label": 1}, {"label": 0}, {"label": 1}, {"label": 0}]
    first = run_zero_shot_binary_predictions(
        "cache-test",
        rows,
        label_key="label",
        cache_enabled=True,
        cache_dir=str(tmp_path),
    )
    second = run_zero_shot_binary_predictions(
        "cache-test",
        rows,
        label_key="label",
        cache_enabled=True,
        cache_dir=str(tmp_path),
    )
    assert first == second


def test_zero_shot_extract_prediction_handles_common_shapes() -> None:
    assert _extract_prediction({"prediction": 1}) == 1
    assert _extract_prediction({"label": "yes"}) == 1
    assert _extract_prediction([{"prediction": 0}]) == 0
    assert _extract_prediction("true") == 1


def test_zero_shot_deterministic_fallback_without_remote(monkeypatch: object, tmp_path: Path) -> None:
    monkeypatch.setenv("EVAL_DISABLE_ZERO_SHOT_LLM", "1")
    rows = [{"label": 1}, {"label": 0}, {"label": 1}, {"label": 0}]
    preds = run_zero_shot_binary_predictions(
        "deterministic-test",
        rows,
        label_key="label",
        cache_enabled=True,
        cache_dir=str(tmp_path),
    )
    assert len(preds) == len(rows)
    assert set(preds).issubset({0, 1})


def test_run_performance_eval_writes_computed_metrics(tmp_path: Path) -> None:
    result = run_performance_eval(tmp_path)

    assert result["benchmark"] == "Performance hotspot detection"
    assert "f1" in result["metrics"]
    assert "f1_ci95" in result["metrics"]
    assert "zero_shot_f1" in result["baseline_zero_shot"]

    output_file = tmp_path / "performance_eval.json"
    assert output_file.exists()
    persisted = json.loads(output_file.read_text(encoding="utf-8"))
    assert persisted["agent"] == "performance_agent"


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
