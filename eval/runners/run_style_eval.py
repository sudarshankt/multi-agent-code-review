from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.config_runtime import load_eval_config
from eval.datasets.prepare_owasp_cwe import prepare_owasp_cwe
from eval.metrics.ablation import compute_style_baseline, compute_style_baseline_from_labels
from eval.metrics.classification import bootstrap_confidence_interval
from eval.optional_dependencies import dependency_status
from eval.zero_shot_baseline import run_zero_shot_binary_predictions


def _compute_radon_spot_check(sample_n: int) -> dict[str, Any]:
    dep = dependency_status("radon", "radon")
    if not dep["available"]:
        return {
            "status": "pending",
            "notes": "radon is not available in the environment.",
            "dependency": dep,
        }

    from radon.complexity import cc_visit  # type: ignore[import-not-found]

    candidate_paths = sorted(Path("tests/test_data").glob("*.py"))[: max(sample_n, 1)]
    if not candidate_paths:
        return {
            "status": "pending",
            "notes": "No local Python sample files were found for radon spot-checking.",
        }

    scores: list[float] = []
    block_scores: list[float] = []
    file_scores: list[float] = []
    for path in candidate_paths:
        blocks = cc_visit(path.read_text(encoding="utf-8"))
        local_scores: list[float] = []
        for block in blocks:
            scores.append(float(block.complexity))
            block_scores.append(float(block.complexity))
            local_scores.append(float(block.complexity))
        file_scores.append(max(local_scores) if local_scores else 0.0)

    if not scores:
        return {
            "status": "implemented",
            "sampled_files": len(candidate_paths),
            "average_cc": 0.0,
            "max_cc": 0.0,
        }

    return {
        "status": "implemented",
        "sampled_files": len(candidate_paths),
        "average_cc": sum(scores) / len(scores),
        "max_cc": max(scores),
        "block_scores": block_scores,
        "file_scores": file_scores,
        "file_paths": [str(path) for path in candidate_paths],
        "dependency": dep,
    }


def _run_pylint_on_file(path: Path) -> bool:
    cmd = [sys.executable, "-m", "pylint", "--output-format=json", str(path)]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception:
        return False

    stdout = completed.stdout.strip()
    if not stdout:
        return False
    try:
        parsed = json.loads(stdout)
    except Exception:
        return False
    return isinstance(parsed, list) and len(parsed) > 0


def _compute_pylint_agreement(file_paths: list[str], gold_labels: list[bool]) -> dict[str, Any]:
    if not file_paths or len(file_paths) != len(gold_labels):
        return {"status": "pending", "agreement": 0.0, "false_positive_rate": 0.0, "n": 0}
    pylint_dep = dependency_status("pylint", "pylint")
    if not pylint_dep.get("available", False):
        return {
            "status": "pending",
            "agreement": 0.0,
            "false_positive_rate": 0.0,
            "n": 0,
            "dependency": pylint_dep,
        }

    predicted_labels = [_run_pylint_on_file(Path(path)) for path in file_paths]
    baseline = compute_style_baseline_from_labels(gold_labels, predicted_labels)
    correctness = [1.0 if g == p else 0.0 for g, p in zip(gold_labels, predicted_labels, strict=True)]
    return {
        "status": "implemented",
        "agreement": baseline["agreement"],
        "false_positive_rate": baseline["false_positive_rate"],
        "agreement_ci95": bootstrap_confidence_interval(correctness),
        "n": len(gold_labels),
        "predicted_positive_rate": sum(1 for label in predicted_labels if label) / len(predicted_labels),
        "predicted_labels": predicted_labels,
        "dependency": pylint_dep,
    }


def run_style_eval(output_dir: str | Path | None = None) -> dict[str, Any]:
    """Evaluate style/performance and include a direct Radon spot-check when available."""
    cfg = load_eval_config()
    dataset_dir = prepare_owasp_cwe()
    radon_metrics = _compute_radon_spot_check(cfg.radon_sample_n)
    if radon_metrics.get("status") == "implemented":
        file_scores = [float(x) for x in radon_metrics.get("file_scores", [])]
        gold_labels = [score >= 5.0 for score in file_scores]
        file_paths = [str(path) for path in radon_metrics.get("file_paths", [])]
        pylint_metrics = _compute_pylint_agreement(file_paths, gold_labels)
        if pylint_metrics.get("status") == "implemented":
            agreement = float(pylint_metrics["agreement"])
            false_positive_rate = float(pylint_metrics["false_positive_rate"])
            agreement_ci95 = list(pylint_metrics["agreement_ci95"])
        else:
            agreement = 0.0
            false_positive_rate = 0.0
            agreement_ci95 = [0.0, 0.0]

        baseline_rows = [{"label": int(label)} for label in gold_labels]
        zero_shot_preds = run_zero_shot_binary_predictions(
            "style_pylint_agreement",
            baseline_rows,
            label_key="label",
            prediction_key="prediction",
            cache_enabled=cfg.cache_enabled,
            cache_dir=cfg.cache_dir,
        )
        zero_shot_bools = [pred == 1 for pred in zero_shot_preds]
        baseline = compute_style_baseline_from_labels(gold_labels[: len(zero_shot_bools)], zero_shot_bools)
    else:
        pylint_metrics = {"status": "pending", "n": 0}
        agreement = 0.0
        false_positive_rate = 0.0
        agreement_ci95 = [0.0, 0.0]
        baseline = compute_style_baseline()
    payload = {
        "benchmark": "Pylint agreement",
        "agent": "style",
        "dataset_path": str(dataset_dir),
        "n": cfg.radon_sample_n,
        "metrics": {
            "agreement": agreement,
            "agreement_ci95": agreement_ci95,
            "false_positive_rate": false_positive_rate,
        },
        "baseline_zero_shot": {
            "agreement": baseline["agreement"],
            "false_positive_rate": baseline["false_positive_rate"],
        },
        "radon_spot_check": radon_metrics,
        "pylint_eval": pylint_metrics,
        "dependency_status": {
            "radon": radon_metrics.get("dependency", dependency_status("radon", "radon")),
            "pylint": pylint_metrics.get("dependency", dependency_status("pylint", "pylint")),
        },
        "benchmark_coverage": [
            {
                "name": "Pylint agreement",
                "status": "implemented" if pylint_metrics.get("status") == "implemented" else "pending",
                "notes": (
                    f"Computed on {pylint_metrics.get('n', 0)} files with radon-derived labels."
                    if pylint_metrics.get("status") == "implemented"
                    else "Pylint results unavailable in current environment."
                ),
            },
            {"name": "Radon complexity ground-truth spot-check", "status": radon_metrics["status"]},
        ],
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or cfg.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "style_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
