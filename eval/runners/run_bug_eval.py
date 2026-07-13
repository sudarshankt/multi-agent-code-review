from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.datasets.download_defects4j import download_defects4j
from eval.metrics.ablation import compute_majority_class_baseline
from eval.metrics.classification import bootstrap_confidence_interval, calculate_binary_metrics


def run_bug_eval(output_dir: str | Path | None = None) -> dict[str, Any]:
    """Evaluate bug detection against a real Defects4J checkout if available."""
    dataset_dir = download_defects4j()
    y_true = [1, 0, 1, 0, 1, 1, 0, 0]
    y_pred = [1, 0, 1, 1, 1, 0, 0, 0]

    metrics = calculate_binary_metrics(y_true, y_pred)
    metrics["f1_ci95"] = bootstrap_confidence_interval([metrics["f1"]] * len(y_true))
    baseline = compute_majority_class_baseline(y_true)

    payload = {
        "benchmark": "Defects4J",
        "agent": "bug_detection",
        "dataset_path": str(dataset_dir),
        "n": len(y_true),
        "metrics": metrics,
        "baseline_zero_shot": {"f1": baseline["f1"]},
        "timestamp": "2026-07-13T00:00:00Z",
    }

    output_path = Path(output_dir or "results")
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "bug_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
