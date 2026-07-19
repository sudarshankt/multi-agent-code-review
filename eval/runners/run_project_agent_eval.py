from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.metrics.classification import (
    bootstrap_confidence_interval,
    calculate_binary_metrics,
)
from eval.metrics.from_project_outputs import load_review_from_json, summarize_findings


def run_project_agent_eval(review_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Evaluate a saved project review artifact using the agent findings in the review model."""
    review = load_review_from_json(review_path)
    summary = summarize_findings(review)

    agent_names = [str(name) for name in summary.get("agents", [])]
    security_true = [1 if "security" in name else 0 for name in agent_names]
    bug_true = [1 if ("bug" in name or "defect" in name) else 0 for name in agent_names]
    security_pred = [int(v) for v in summary.get("security_labels", [])][: len(security_true)]
    bug_pred = [int(v) for v in summary.get("bug_labels", [])][: len(bug_true)]

    security_metrics = calculate_binary_metrics(security_true, security_pred) if security_true else {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    bug_metrics = calculate_binary_metrics(bug_true, bug_pred) if bug_true else {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    security_baseline_pred = [0] * len(security_true)
    bug_baseline_pred = [0] * len(bug_true)
    security_baseline = calculate_binary_metrics(security_true, security_baseline_pred) if security_true else {"f1": 0.0}
    bug_baseline = calculate_binary_metrics(bug_true, bug_baseline_pred) if bug_true else {"f1": 0.0}

    security_correctness = [1.0 if t == p else 0.0 for t, p in zip(security_true, security_pred, strict=True)] if security_true else []
    bug_correctness = [1.0 if t == p else 0.0 for t, p in zip(bug_true, bug_pred, strict=True)] if bug_true else []

    payload = {
        "benchmark": "Project agent review",
        "agent": "project_agents",
        "source_review": str(review_path),
        "n": summary["agent_count"],
        "metrics": {
            "security_f1": security_metrics.get("f1", 0.0),
            "security_f1_ci95": bootstrap_confidence_interval(security_correctness) if security_correctness else [0.0, 0.0],
            "bug_f1": bug_metrics.get("f1", 0.0),
            "bug_f1_ci95": bootstrap_confidence_interval(bug_correctness) if bug_correctness else [0.0, 0.0],
            "total_findings": summary["total_findings"],
        },
        "baseline_zero_shot": {
            "security_f1": security_baseline.get("f1", 0.0),
            "bug_f1": bug_baseline.get("f1", 0.0),
        },
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or "results")
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "project_agent_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
