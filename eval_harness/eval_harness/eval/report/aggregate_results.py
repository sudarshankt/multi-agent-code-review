"""Merge every runner's result JSON (results/*.json) into one
final_report.json and a rendered final_report.md, per Section 6 of the
instructions doc.

Usage:
    python -m eval.report.aggregate_results
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from eval.common import REPO_ROOT, load_config


def collect_results(results_dir: Path) -> list[dict]:
    records = []
    for f in sorted(results_dir.glob("*.json")):
        if f.name in ("final_report.json",):
            continue
        with open(f) as fh:
            try:
                records.append(json.load(fh))
            except json.JSONDecodeError:
                print(f"[aggregate] skipping malformed JSON: {f}")
    return records


def _fmt_metric(v) -> str:
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, dict):
        return json.dumps(v)
    return str(v)


def render_markdown(records: list[dict]) -> str:
    lines = [
        "# Evaluation Report — Team 10",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        "| Agent | Benchmark | n | Key metrics | Meets target? | Zero-shot baseline |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        metrics = r.get("metrics", {})
        key_bits = []
        for k in ("f1", "precision", "recall", "pass_rate", "clean_pass_rate", "agreement", "faithfulness", "answer_relevancy"):
            if k in metrics:
                key_bits.append(f"{k}={_fmt_metric(metrics[k])}")
        meets = metrics.get("meets_target")
        meets_str = "✅" if meets is True else ("❌" if meets is False else "—")
        baseline = r.get("baseline_zero_shot") or {}
        baseline_str = _fmt_metric(baseline.get("f1")) if "f1" in baseline else "—"

        lines.append(
            f"| {r.get('agent', '?')} | {r.get('benchmark', '?')} | {r.get('n', '?')} "
            f"| {', '.join(key_bits) or '—'} | {meets_str} | {baseline_str} |"
        )

    lines += [
        "",
        "## Notes",
        "- Benchmarks marked `NOT IMPLEMENTED` in their runner (see console output when",
        "  the runner was invoked) are absent from this table entirely until wired up.",
        "- Defects4J entries for Bug/Patch agents are cross-language sanity checks only",
        "  (see config.yaml `bug_agent_language_note`), not headline numbers.",
        "- \"Zero-shot baseline\" is the single-LLM-call ablation (Section 4) — compare",
        "  against the agent's own F1 to see the delta the multi-agent + RAG pipeline adds.",
        "",
    ]
    return "\n".join(lines)


def aggregate(results_dir: Path | None = None) -> tuple[Path, Path]:
    cfg = load_config()
    results_dir = results_dir or REPO_ROOT / cfg["paths"]["results_dir"]
    records = collect_results(results_dir)

    final_json = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_records": len(records),
        "records": records,
    }
    json_path = results_dir / "final_report.json"
    with open(json_path, "w") as f:
        json.dump(final_json, f, indent=2)

    md_path = results_dir / "final_report.md"
    with open(md_path, "w") as f:
        f.write(render_markdown(records))

    print(f"[aggregate] {len(records)} result files merged.")
    print(f"[aggregate] wrote {json_path}")
    print(f"[aggregate] wrote {md_path}")
    return json_path, md_path


if __name__ == "__main__":
    aggregate()
