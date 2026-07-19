from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.config_runtime import load_eval_config


def _pick_primary_metric(item: dict[str, Any]) -> tuple[str, float, float]:
    metrics = item.get("metrics", {}) if isinstance(item.get("metrics", {}), dict) else {}
    baseline = item.get("baseline_zero_shot", {}) if isinstance(item.get("baseline_zero_shot", {}), dict) else {}
    for key in ["f1", "patch_pass_rate", "agreement", "faithfulness", "security_f1"]:
        if key in metrics:
            return key, float(metrics.get(key, 0.0)), float(baseline.get(key, 0.0))
    return "n/a", 0.0, 0.0


def run_ablation_eval(
    output_dir: str | Path | None = None,
    reference_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize multi-agent uplift over zero-shot baselines across benchmark outputs."""
    cfg = load_eval_config()

    comparisons: list[dict[str, Any]] = []
    for item in reference_results or []:
        metric_name, value, baseline_value = _pick_primary_metric(item)
        if metric_name == "n/a":
            continue
        comparisons.append(
            {
                "benchmark": item.get("benchmark", "N/A"),
                "agent": item.get("agent", "unknown"),
                "metric": metric_name,
                "value": value,
                "baseline": baseline_value,
                "delta": value - baseline_value,
            }
        )

    avg_delta = (
        sum(row["delta"] for row in comparisons) / len(comparisons)
        if comparisons
        else 0.0
    )

    payload = {
        "benchmark": "Ablation baseline",
        "agent": "all",
        "n": len(comparisons) or max(cfg.primevul_n, cfg.defects4j_n, cfg.secbench_n),
        "metrics": {"avg_delta": avg_delta, "benchmark_count": len(comparisons)},
        "baseline_zero_shot": {"avg_delta": 0.0},
        "comparisons": comparisons,
        "benchmark_coverage": [
            {
                "name": "Zero-shot single-LLM baseline across all benchmark families",
                "status": "implemented" if comparisons else "pending",
                "notes": (
                    f"Computed uplift against {len(comparisons)} benchmark outputs."
                    if comparisons
                    else "No benchmark outputs were available to compare against baseline values."
                ),
            }
        ],
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or cfg.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "ablation_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
