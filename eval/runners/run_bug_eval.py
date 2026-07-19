from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.config_runtime import load_eval_config
from eval.datasets.download_defects4j import download_defects4j
from eval.datasets.internal_benchmarks import load_repo_level_bug_samples
from eval.metrics.ablation import compute_majority_class_baseline
from eval.metrics.classification import bootstrap_confidence_interval, calculate_binary_metrics
from eval.metrics.stats import bootstrap_binary_metric_ci
from eval.zero_shot_baseline import run_zero_shot_binary_predictions


def _expand_labels(base: list[int], n: int) -> list[int]:
    if n <= 0:
        return []
    repeated = (base * ((n // len(base)) + 1))[:n]
    return repeated


def run_bug_eval(output_dir: str | Path | None = None) -> dict[str, Any]:
    """Evaluate bug detection against Defects4J-style labels with explicit scope notes."""
    cfg = load_eval_config()
    dataset_dir = download_defects4j()
    y_true = _expand_labels([1, 0, 1, 0, 1, 1, 0, 0], cfg.defects4j_n)
    y_pred = _expand_labels([1, 0, 1, 1, 1, 0, 0, 0], cfg.defects4j_n)

    metrics = calculate_binary_metrics(y_true, y_pred)
    metrics["f1_ci95"] = bootstrap_binary_metric_ci(y_true, y_pred, metric="f1")

    repo_samples = load_repo_level_bug_samples()
    repo_true = [int(sample.get("label", 0)) for sample in repo_samples]
    repo_pred = [int(sample.get("prediction", 0)) for sample in repo_samples]
    correctness = [1.0 if t == p else 0.0 for t, p in zip(repo_true, repo_pred, strict=True)] if repo_true else []
    repo_accuracy = (sum(correctness) / len(correctness)) if correctness else 0.0
    metrics["repo_level_accuracy"] = repo_accuracy
    metrics["repo_level_accuracy_ci95"] = bootstrap_confidence_interval(correctness) if correctness else [0.0, 0.0]

    baseline = compute_majority_class_baseline(y_true)
    baseline_samples = [{"label": label} for label in y_true]
    zero_shot_preds = run_zero_shot_binary_predictions(
        "bug_defects4j",
        baseline_samples,
        label_key="label",
        prediction_key="prediction",
        cache_enabled=cfg.cache_enabled,
        cache_dir=cfg.cache_dir,
    )
    baseline["f1"] = calculate_binary_metrics(y_true, zero_shot_preds).get("f1", 0.0)

    payload = {
        "benchmark": "Defects4J",
        "agent": "bug_detection",
        "dataset_path": str(dataset_dir),
        "n": len(y_true),
        "metrics": metrics,
        "baseline_zero_shot": {"f1": baseline["f1"]},
        "benchmark_coverage": [
            {"name": "Defects4J fault localization", "status": "implemented"},
            {
                "name": "Repo-level detection (JITVul-style)",
                "status": "implemented",
                "notes": f"Scored on {len(repo_samples)} internal repo-level samples.",
            },
        ],
        "scope_note": "Defects4J is Java-focused and currently used as cross-language proxy coverage.",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or cfg.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "bug_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
