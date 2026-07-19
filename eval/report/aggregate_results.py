from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PRIMARY_METRIC_KEYS = ["f1", "patch_pass_rate", "agreement", "faithfulness", "security_f1", "avg_delta"]


def _pick_primary_metric(metrics: dict[str, Any], baseline: dict[str, Any]) -> tuple[str, float, float]:
    for key in _PRIMARY_METRIC_KEYS:
        if key in metrics:
            return key, float(metrics.get(key, 0.0)), float(baseline.get(key, 0.0))
    return "n/a", 0.0, 0.0


def build_report_payload(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a summary payload for the evaluation report."""
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "count": len(results),
            "agents": sorted({item.get("agent", "unknown") for item in results}),
        },
        "results": results,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a compact markdown table from the report payload."""
    lines = [
        "# Evaluation Report",
        "",
        "| Benchmark | Agent | Metric | Value | Baseline |",
        "|---|---|---|---:|---:|",
    ]

    for item in report.get("results", []):
        metrics = item.get("metrics", {})
        baseline = item.get("baseline_zero_shot", {})
        metric_name, value, baseline_value = _pick_primary_metric(metrics, baseline)
        lines.append(
            f"| {item.get('benchmark', 'N/A')} | {item.get('agent', 'N/A')} | {metric_name} | {value:.3f} | {baseline_value:.3f} |"
        )

    return "\n".join(lines)


def write_report_files(report: dict[str, Any], output_dir: str | Path | None = None) -> tuple[Path, Path]:
    """Write JSON and markdown report files to disk."""
    output_path = Path(output_dir or "results")
    output_path.mkdir(parents=True, exist_ok=True)

    json_path = output_path / "final_report.json"
    markdown_path = output_path / "final_report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return json_path, markdown_path
