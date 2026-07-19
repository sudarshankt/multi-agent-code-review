from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.config_runtime import load_eval_config
from eval.datasets.download_defects4j import download_defects4j
from eval.datasets.download_secbench import download_secbench
from eval.datasets.internal_benchmarks import (
    load_defects4j_patch_samples,
    load_patcheval_samples,
    load_secbench_patch_samples,
    summarize_binary_rate,
)
from eval.metrics.ablation import compute_patch_baseline_from_outcomes
from eval.metrics.classification import bootstrap_confidence_interval
from eval.zero_shot_baseline import run_zero_shot_binary_predictions


def _load_human_patch_review(path: str | Path = "eval/human_eval/patch_review.csv") -> tuple[float, int]:
    review_path = Path(path)
    if not review_path.exists():
        return 0.0, 0

    import csv

    with review_path.open("r", encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if isinstance(row, dict)]
    rated_rows = [row for row in rows if str(row.get("pass", "")).strip()]
    if not rated_rows:
        return 0.0, 0
    rate, n = summarize_binary_rate(rated_rows, "pass")
    return rate, n


def run_patch_eval(output_dir: str | Path | None = None) -> dict[str, Any]:
    """Evaluate patch generation with SEC-bench metrics and patch benchmark coverage notes."""
    cfg = load_eval_config()
    dataset_dir = download_secbench()
    defects4j_dir = download_defects4j()
    patcheval_samples = load_patcheval_samples()
    patch_eval_correctness, patch_eval_n = summarize_binary_rate(patcheval_samples, "correct")
    human_review_rate, human_review_n = _load_human_patch_review()
    secbench_samples = load_secbench_patch_samples()
    patch_outcomes = [bool(sample.get("patch_pass", False)) for sample in secbench_samples]
    poc_outcomes = [bool(sample.get("poc_reproduced", False)) for sample in secbench_samples]
    patch_pass_rate = (sum(1 for item in patch_outcomes if item) / len(patch_outcomes)) if patch_outcomes else 0.0
    poc_reproduction_rate = (sum(1 for item in poc_outcomes if item) / len(poc_outcomes)) if poc_outcomes else 0.0

    d4j_samples = load_defects4j_patch_samples()
    valid_patch_outcomes = [
        bool(sample.get("tests_pass", False)) and (not bool(sample.get("touched_test_files", False)))
        for sample in d4j_samples
    ]
    defects4j_patch_pass_rate = (
        sum(1 for outcome in valid_patch_outcomes if outcome) / len(valid_patch_outcomes)
        if valid_patch_outcomes
        else 0.0
    )
    baseline = compute_patch_baseline_from_outcomes(patch_outcomes)
    baseline_preds = run_zero_shot_binary_predictions(
        "secbench_patch_pass",
        secbench_samples,
        label_key="patch_pass",
        prediction_key="prediction",
        cache_enabled=cfg.cache_enabled,
        cache_dir=cfg.cache_dir,
    )
    if patch_outcomes and len(baseline_preds) == len(patch_outcomes):
        baseline["patch_pass_rate"] = sum(1 for pred in baseline_preds if pred == 1) / len(baseline_preds)
        baseline_correctness = [1.0 if int(true_value) == pred else 0.0 for true_value, pred in zip(patch_outcomes, baseline_preds, strict=True)]
        baseline["patch_pass_rate_ci95"] = bootstrap_confidence_interval(baseline_correctness)
    else:
        baseline["patch_pass_rate_ci95"] = [0.0, 0.0]

    payload = {
        "benchmark": "SEC-bench",
        "agent": "patch_generation",
        "dataset_path": str(dataset_dir),
        "defects4j_dataset_path": str(defects4j_dir),
        "n": cfg.secbench_n,
        "metrics": {
            "patch_pass_rate": patch_pass_rate,
            "patch_pass_rate_ci95": bootstrap_confidence_interval([1.0 if item else 0.0 for item in patch_outcomes]) if patch_outcomes else [0.0, 0.0],
            "po_c_reproduction_rate": poc_reproduction_rate,
            "po_c_reproduction_rate_ci95": bootstrap_confidence_interval([1.0 if item else 0.0 for item in poc_outcomes]) if poc_outcomes else [0.0, 0.0],
            "defects4j_patch_pass_rate": defects4j_patch_pass_rate,
            "defects4j_patch_pass_rate_ci95": bootstrap_confidence_interval([1.0 if item else 0.0 for item in valid_patch_outcomes]) if valid_patch_outcomes else [0.0, 0.0],
            "patch_eval_correctness": patch_eval_correctness,
            "human_patch_review_pass_rate": human_review_rate,
        },
        "baseline_zero_shot": {
            "patch_pass_rate": baseline["patch_pass_rate"],
            "patch_pass_rate_ci95": baseline["patch_pass_rate_ci95"],
        },
        "benchmark_coverage": [
            {
                "name": "Defects4J patch pass rate",
                "status": "implemented",
                "notes": f"Computed on {len(valid_patch_outcomes)} local Defects4J-style patch samples with test-file guard.",
            },
            {"name": "SEC-bench", "status": "implemented"},
            {
                "name": "PatchEval",
                "status": "implemented",
                "notes": f"Scored on {patch_eval_n} local PatchEval-style samples.",
            },
            {
                "name": "SEC-bench patch pass / PoC reproduction",
                "status": "implemented",
                "notes": f"Scored on {len(secbench_samples)} local SEC-bench-style samples.",
            },
            {
                "name": "Human-reviewed patch sample",
                "status": "implemented" if human_review_n > 0 else "pending",
                "notes": (
                    f"Scored on {human_review_n} reviewed patch rows."
                    if human_review_n > 0
                    else "No reviewed rows with pass/fail labels were found yet."
                ),
            },
        ],
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or cfg.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "patch_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
