from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any


def extract_series(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract a simple chartable series from the report payload."""
    series: list[dict[str, Any]] = []
    for item in report.get("results", []):
        metrics = item.get("metrics", {})
        baseline = item.get("baseline_zero_shot", {})
        primary_metric = None
        primary_value = None
        baseline_value = None

        if "f1" in metrics:
            primary_metric = "f1"
            primary_value = metrics["f1"]
            baseline_value = baseline.get("f1")
        elif "patch_pass_rate" in metrics:
            primary_metric = "patch_pass_rate"
            primary_value = metrics["patch_pass_rate"]
            baseline_value = baseline.get("patch_pass_rate")
        elif "agreement" in metrics:
            primary_metric = "agreement"
            primary_value = metrics["agreement"]
            baseline_value = baseline.get("agreement")
        elif "faithfulness" in metrics:
            primary_metric = "faithfulness"
            primary_value = metrics["faithfulness"]
            baseline_value = baseline.get("faithfulness")

        if primary_metric and primary_value is not None:
            series.append(
                {
                    "benchmark": item.get("benchmark", "N/A"),
                    "agent": item.get("agent", "unknown"),
                    "metric": primary_metric,
                    "value": primary_value,
                    "baseline": baseline_value,
                }
            )

    return series


def render_html_report(report_path: str | Path) -> str:
    """Render a simple HTML page with bar charts for the evaluation results."""
    report_path = Path(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    series = extract_series(report)

    bars = []
    for point in series:
        value = point["value"]
        baseline = point.get("baseline") or 0.0
        bars.append(
            f"<div class='bar-row'><div class='label'>{escape(point['benchmark'])}</div><div class='bar-track'><div class='bar-value' style='width:{value * 100:.1f}%'></div></div><div class='value'>{value:.2f}</div><div class='baseline'>baseline {baseline:.2f}</div></div>"
        )

    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>Evaluation Results</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; color: #1f2937; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .summary {{ color: #4b5563; margin-bottom: 1.5rem; }}
    .bar-row {{ display: grid; grid-template-columns: 180px 1fr 60px 90px; gap: 0.75rem; align-items: center; margin-bottom: 0.75rem; }}
    .bar-track {{ background: #e5e7eb; border-radius: 999px; overflow: hidden; height: 12px; }}
    .bar-value {{ background: linear-gradient(90deg, #2563eb, #38bdf8); height: 100%; }}
    .value {{ font-weight: 600; }}
    .baseline {{ color: #6b7280; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>Evaluation Results</h1>
  <div class='summary'>Generated from {report_path.name} with {len(series)} chartable metrics.</div>
  {''.join(bars)}
</body>
</html>"""


def write_html_report(report_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Write an HTML report for the evaluation results."""
    report_path = Path(report_path)
    output_path = Path(output_path or report_path.parent / "evaluation_results.html")
    output_path.write_text(render_html_report(report_path), encoding="utf-8")
    return output_path
