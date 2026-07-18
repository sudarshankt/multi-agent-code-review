from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

_PRIMARY_METRIC_KEYS = ["f1", "patch_pass_rate", "agreement", "faithfulness", "security_f1"]

_AGENT_ICONS: dict[str, str] = {
    "security": "🔒",
    "bug_detection": "🐛",
    "patch_generation": "🔧",
    "style": "📐",
    "rag": "🔍",
    "all": "🤝",
    "project_agents": "🔗",
}


def extract_series(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract a chartable series from the report payload."""
    series: list[dict[str, Any]] = []
    for item in report.get("results", []):
        metrics = item.get("metrics", {})
        baseline = item.get("baseline_zero_shot", {})
        primary_metric = next((k for k in _PRIMARY_METRIC_KEYS if k in metrics), None)
        if primary_metric is None:
            continue
        primary_value = metrics[primary_metric]
        baseline_value = baseline.get(primary_metric, 0.0)
        improvement = primary_value - baseline_value
        series.append(
            {
                "benchmark": item.get("benchmark", "N/A"),
                "agent": item.get("agent", "unknown"),
                "metric": primary_metric,
                "value": primary_value,
                "baseline": baseline_value,
                "improvement": improvement,
                "n": item.get("n", 0),
                "timestamp": item.get("timestamp", ""),
                "all_metrics": metrics,
            }
        )
    return series


def render_html_report(report_path: str | Path) -> str:
    """Render a full HTML dashboard for the evaluation results."""
    report_path = Path(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    series = extract_series(report)
    generated_at = report.get("generated_at", "")
    n_benchmarks = report.get("summary", {}).get("count", len(series))

    bar_rows: list[str] = []
    for pt in series:
        value = pt["value"]
        baseline = pt["baseline"]
        improvement = pt["improvement"]
        pct = value * 100
        delta_str = (
            f'<span class="delta up">+{improvement * 100:.1f}%</span>'
            if improvement > 0
            else '<span class="delta neutral">Stable</span>'
        )
        icon = _AGENT_ICONS.get(pt["agent"], "🤖")
        extra: list[str] = []
        for k, v in pt["all_metrics"].items():
            if k != pt["metric"] and isinstance(v, (int, float)) and not isinstance(v, bool):
                extra.append(f"<span class='sub-metric'>{escape(k)}: {v:.2f}</span>")
        extra_html = " ".join(extra[:3])
        bar_rows.append(
            f"""<tr>
  <td><strong>{icon} {escape(pt['agent'])}</strong></td>
  <td>{escape(pt['benchmark'])}</td>
  <td>{escape(pt['metric'])}</td>
  <td>
    <div class="bar-wrap">
      <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>
      <span class="bar-label">{value:.3f}</span>
    </div>
  </td>
  <td>{baseline:.3f}</td>
  <td>{delta_str}</td>
  <td>{pt['n']}</td>
  <td class="sub-metrics">{extra_html}</td>
</tr>"""
        )

    kpis = [
        ("📊", str(n_benchmarks), "Benchmarks"),
        ("🤖", str(len({pt["agent"] for pt in series})), "Agents"),
        ("⭐", f"{max((pt['value'] for pt in series), default=0) * 100:.0f}%", "Best Score"),
        ("📈", f"+{sum(pt['improvement'] for pt in series if pt['improvement'] > 0) / max(len([p for p in series if p['improvement'] > 0]), 1) * 100:.1f}%", "Avg Improvement"),
    ]
    kpi_html = "\n".join(
        f"<div class='kpi'><div class='kpi-icon'>{icon}</div><div class='kpi-val'>{val}</div><div class='kpi-lbl'>{lbl}</div></div>"
        for icon, val, lbl in kpis
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Evaluation Results — Multi-Agent Code Review</title>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f3f4f6;color:#1f2937}}
    .banner{{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:2.5rem 2rem;text-align:center}}
    .banner h1{{font-size:2.2rem;font-weight:800;margin-bottom:.4rem}}
    .banner .meta{{font-size:.9rem;opacity:.8;margin-top:.5rem}}
    .page{{max-width:1200px;margin:0 auto;padding:2rem 1.5rem}}
    .kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:1.25rem;margin-bottom:2rem}}
    .kpi{{background:#fff;border-radius:12px;padding:1.5rem;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.08);border-top:4px solid #7c3aed}}
    .kpi-icon{{font-size:1.8rem;margin-bottom:.4rem}}
    .kpi-val{{font-size:2rem;font-weight:800;color:#1f2937}}
    .kpi-lbl{{font-size:.78rem;color:#6b7280;font-weight:600;text-transform:uppercase;margin-top:.2rem}}
    .card{{background:#fff;border-radius:12px;padding:2rem;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:2rem}}
    .card h2{{font-size:1.3rem;font-weight:700;margin-bottom:1.25rem;color:#1f2937;border-bottom:2px solid #7c3aed;padding-bottom:.5rem}}
    table{{width:100%;border-collapse:collapse;font-size:.88rem}}
    th{{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:.8rem 1rem;text-align:left;font-weight:700;font-size:.78rem;text-transform:uppercase}}
    td{{padding:.75rem 1rem;border-bottom:1px solid #f3f4f6;vertical-align:middle}}
    tr:last-child td{{border-bottom:none}}
    tr:hover{{background:#f9fafb}}
    .bar-wrap{{display:flex;align-items:center;gap:.6rem}}
    .bar-track{{flex:1;background:#e5e7eb;border-radius:999px;height:8px;overflow:hidden;max-width:140px}}
    .bar-fill{{height:100%;background:linear-gradient(90deg,#6366f1,#8b5cf6);border-radius:999px}}
    .bar-label{{font-weight:700;font-size:.88rem;min-width:38px}}
    .delta.up{{color:#16a34a;font-weight:700}}
    .delta.neutral{{color:#0d9488;font-weight:700}}
    .sub-metrics{{font-size:.75rem;color:#6b7280}}
    .sub-metric{{display:inline-block;background:#f3f4f6;border-radius:6px;padding:.15rem .45rem;margin:.1rem}}
    footer{{text-align:center;color:#9ca3af;font-size:.8rem;padding:2rem 0 3rem}}
    @media(max-width:640px){{.kpi-row{{grid-template-columns:repeat(2,1fr)}}}}
  </style>
</head>
<body>
<div class="banner">
  <h1>🤖 Multi-Agent Code Review — Evaluation Results</h1>
  <div class="meta">Generated: {escape(generated_at)} &nbsp;·&nbsp; Source: {escape(report_path.name)} &nbsp;·&nbsp; {n_benchmarks} benchmarks</div>
</div>
<div class="page">
  <div class="kpi-row">{kpi_html}</div>
  <div class="card">
    <h2>📊 Benchmark Results</h2>
    <div style="overflow-x:auto">
      <table>
        <thead><tr><th>Agent</th><th>Benchmark</th><th>Metric</th><th>Score</th><th>Baseline</th><th>Improvement</th><th>n</th><th>Other Metrics</th></tr></thead>
        <tbody>{''.join(bar_rows)}</tbody>
      </table>
    </div>
  </div>
</div>
<footer>Multi-Agent Code Review &nbsp;·&nbsp; Evaluation Run: {escape(generated_at)}</footer>
</body>
</html>"""


def write_html_report(report_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Write an HTML report for the evaluation results to disk."""
    report_path = Path(report_path)
    output_path = Path(output_path or report_path.parent / "evaluation_results.html")
    output_path.write_text(render_html_report(report_path), encoding="utf-8")
    return output_path
