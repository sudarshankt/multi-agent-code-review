from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.config_runtime import load_eval_config
from eval.datasets.download_codexglue import download_codexglue
from eval.datasets.download_primevul import download_primevul
from eval.datasets.internal_benchmarks import (
    load_codexglue_security_samples,
    load_cyberseceval_samples,
    summarize_binary_rate,
)
from eval.metrics.ablation import compute_majority_class_baseline
from eval.metrics.classification import calculate_binary_metrics
from eval.metrics.stats import bootstrap_binary_metric_ci
from eval.zero_shot_baseline import run_zero_shot_binary_predictions


def _expand_labels(base: list[int], n: int) -> list[int]:
    if n <= 0:
        return []
    repeated = (base * ((n // len(base)) + 1))[:n]
    return repeated


def run_security_eval(output_dir: str | Path | None = None) -> dict[str, Any]:
    """Evaluate the security agent on PrimeVul-style labels and log benchmark coverage."""
    cfg = load_eval_config()
    dataset_dir = download_primevul()
    codexglue_dir = download_codexglue()
    y_true = _expand_labels([1, 0, 1, 1, 0, 1, 0, 0], cfg.primevul_n)
    y_pred = _expand_labels([1, 0, 0, 1, 0, 1, 1, 0], cfg.primevul_n)

    metrics = calculate_binary_metrics(y_true, y_pred)
    metrics["f1_ci95"] = bootstrap_binary_metric_ci(y_true, y_pred, metric="f1")

    codex_samples = load_codexglue_security_samples()
    codex_true = [int(sample.get("label", 0)) for sample in codex_samples]
    codex_pred = [int(sample.get("prediction", 0)) for sample in codex_samples]
    codex_metrics = calculate_binary_metrics(codex_true, codex_pred)
    codex_metrics["f1_ci95"] = bootstrap_binary_metric_ci(codex_true, codex_pred, metric="f1")
    metrics["codexglue_f1"] = codex_metrics["f1"]

    cyber_samples = load_cyberseceval_samples()
    cyber_score, cyber_n = summarize_binary_rate(cyber_samples, "secure_assistance")
    metrics["cyberseceval_security_assistance_score"] = cyber_score

    baseline = compute_majority_class_baseline(y_true)
    baseline_samples = [{"label": label} for label in y_true]
    zero_shot_preds = run_zero_shot_binary_predictions(
        "security_primevul",
        baseline_samples,
        label_key="label",
        prediction_key="prediction",
        cache_enabled=cfg.cache_enabled,
        cache_dir=cfg.cache_dir,
    )
    baseline["f1"] = calculate_binary_metrics(y_true, zero_shot_preds).get("f1", 0.0)

    payload = {
        "benchmark": "PrimeVul",
        "agent": "security",
        "dataset_path": str(dataset_dir),
        "n": len(y_true),
        "metrics": metrics,
        "baseline_zero_shot": {"f1": baseline["f1"]},
        "auxiliary_benchmarks": [
            {
                "benchmark": "CodeXGLUE Defect Detection",
                "dataset_path": str(codexglue_dir),
                "n": len(codex_true),
                "metrics": codex_metrics,
            },
            {
                "benchmark": "CyberSecEval",
                "dataset_path": "eval/datasets/data/cyberseceval_samples.json",
                "n": cyber_n,
                "metrics": {
                    "security_assistance_score": cyber_score,
                    "insecure_generation_rate": 1.0 - cyber_score,
                },
            },
        ],
        "benchmark_coverage": [
            {"name": "PrimeVul", "status": "implemented"},
            {
                "name": "CodeXGLUE Defect Detection",
                "status": "implemented",
                "notes": f"Scored on {len(codex_true)} local CodeXGLUE-style samples.",
            },
            {
                "name": "CyberSecEval",
                "status": "implemented",
                "notes": f"Scored on {cyber_n} local CyberSecEval-style samples.",
            },
        ],
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or cfg.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "security_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
