from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.config_runtime import load_eval_config
from eval.datasets.internal_benchmarks import load_performance_samples
from eval.metrics.ablation import compute_majority_class_baseline
from eval.metrics.classification import (
    bootstrap_confidence_interval,
    calculate_binary_metrics,
)
from eval.metrics.stats import bootstrap_binary_metric_ci
from eval.zero_shot_baseline import run_zero_shot_binary_predictions


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return 1 if value != 0 else 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "y"} else 0


def run_performance_eval(output_dir: str | Path = "results") -> dict[str, Any]:
    config = load_eval_config()
    rows = load_performance_samples()

    y_true = [_to_int(r.get("hotspot", 0)) for r in rows]
    y_pred = [_to_int(r.get("prediction", 0)) for r in rows]

    metrics = calculate_binary_metrics(y_true, y_pred)
    metrics["f1_ci95"] = bootstrap_binary_metric_ci(y_true, y_pred, metric="f1")

    z_preds = run_zero_shot_binary_predictions(
        "performance_hotspot_detection",
        rows,
        label_key="hotspot",
        prediction_key="prediction",
        cache_enabled=config.cache_enabled,
        cache_dir=config.cache_dir,
    )
    baseline = compute_majority_class_baseline(y_true)
    baseline["zero_shot_f1"] = calculate_binary_metrics(y_true, z_preds).get("f1", 0.0)
    baseline_correctness = [1.0 if t == p else 0.0 for t, p in zip(y_true, z_preds, strict=True)] if y_true else []
    baseline["zero_shot_f1_ci95"] = bootstrap_confidence_interval(baseline_correctness) if baseline_correctness else [0.0, 0.0]

    payload = {
        "benchmark": "Performance hotspot detection",
        "agent": "performance_agent",
        "n": len(y_true),
        "metrics": {
            "precision": metrics.get("precision", 0.0),
            "recall": metrics.get("recall", 0.0),
            "f1": metrics.get("f1", 0.0),
            "f1_ci95": metrics["f1_ci95"],
        },
        "baseline_zero_shot": baseline,
        "benchmark_coverage": {
            "hotspot_detection": {
                "implemented": True,
                "source": "eval/datasets/data/performance_samples.json",
                "notes": "Binary performance hotspot labels with CI",
            }
        },
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "performance_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
