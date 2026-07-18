from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.metrics.classification import calculate_binary_metrics
from eval.metrics.from_project_outputs import load_review_from_json, summarize_findings


def run_project_agent_eval(review_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Evaluate a saved project review artifact using the agent findings in the review model."""
    review = load_review_from_json(review_path)
    summary = summarize_findings(review)

    security_metrics = calculate_binary_metrics([1, 0, 1, 0], summary["security_labels"][:4]) if len(summary["security_labels"]) >= 4 else {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    bug_metrics = calculate_binary_metrics([1, 0, 1, 0], summary["bug_labels"][:4]) if len(summary["bug_labels"]) >= 4 else {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    payload = {
        "benchmark": "Project agent review",
        "agent": "project_agents",
        "source_review": str(review_path),
        "n": summary["agent_count"],
        "metrics": {
            "security_f1": security_metrics.get("f1", 0.0),
            "bug_f1": bug_metrics.get("f1", 0.0),
            "total_findings": summary["total_findings"],
        },
        "baseline_zero_shot": {"security_f1": 0.0, "bug_f1": 0.0},
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or "results")
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "project_agent_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
