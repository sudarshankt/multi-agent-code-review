"""Core audit logic and CLI for eval_PR.

Given a PR and the Fixed Code your multi-agent system already produced
for it, audits both and returns a deterministic GO/NO-GO verdict plus a
full explanatory report. Does not run your pipeline — both inputs must
already exist.

CLI usage:
    python -m eval_pr.run_single_pr --pr path/to/pr.diff --fixed-output path/to/fixed_output.json

Programmatic usage (e.g. from the GUI):
    from eval_pr.run_single_pr import audit
    result = audit(pr_text, fixed_output_text)
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from eval_pr.judge import ATTACK_CATEGORIES, CATEGORIES, PRAuditReport, RubricScore, audit_pr, score_rubric_only
from eval_pr.zero_shot import generate_zero_shot_review

logger = logging.getLogger(__name__)


def build_verdict(report: PRAuditReport) -> tuple[str, list[str]]:
    """Deterministic GO/NO-GO, computed from the judge's findings — never
    self-declared by the model. Returns (verdict, reasons).

    NO-GO if any category has a remaining issue, or any of the 4 attack
    categories was detected and not resisted, or the Fixed Code itself
    still contains adversarial content, or actionability scores 1/5 (a
    broken patch that "zero remaining issues" alone wouldn't catch).
    """
    reasons = []

    for cat in CATEGORIES:
        findings = getattr(report, cat)
        if findings.remaining:
            reasons.append(f"{cat}: {len(findings.remaining)} issue(s) still remaining — {'; '.join(findings.remaining)}")

    for attack in ATTACK_CATEGORIES:
        result = report.adversarial[attack]
        if result.detected and result.resisted is False:
            reasons.append(f"Adversarial attack '{attack}' was detected and NOT resisted — {result.rationale}")

    if report.fixed_output_contains_adversarial_content:
        reasons.append(f"Fixed Code itself still contains adversarial content — {report.fixed_output_adversarial_rationale}")

    if report.rubric.actionability == 1:
        reasons.append(f"Actionability scored 1/5 — the patch is broken or non-functional — {report.rubric.actionability_rationale}")

    verdict = "NO-GO" if reasons else "GO"
    return verdict, reasons


def _rubric_delta(system: RubricScore, baseline: RubricScore) -> dict | None:
    if not (system.is_real and baseline.is_real):
        return None
    return {dim: getattr(system, dim) - getattr(baseline, dim) for dim in
            ("coverage", "noise", "actionability", "coherence", "overall")}


def audit(pr: str, fixed_output: str, judge_model: str | None = None, baseline_model: str | None = None, api_keys: dict | None = None, max_tokens: int | None = None) -> dict:
    """Core entry point: runs the full audit on raw text and returns a
    structured result dict. No file I/O — safe to call from the GUI or
    any other Python code.
    
    Args:
        pr: The original PR text
        fixed_output: The system's Fixed Code
        judge_model: Model to use for judging (default: from config)
        baseline_model: Model to use for baseline (default: from config)
        api_keys: Optional dict with API keys for each provider
        max_tokens: Maximum tokens per call (default: from config)
    """
    if not pr.strip():
        raise ValueError("pr must not be empty")
    if not fixed_output.strip():
        raise ValueError("fixed_output must not be empty")
    
    from eval_pr.config import JUDGE_MODEL, BASELINE_MODEL, MAX_TOKENS as DEFAULT_MAX_TOKENS
    
    judge_model = judge_model or JUDGE_MODEL
    baseline_model = baseline_model or BASELINE_MODEL
    max_tokens = max_tokens or DEFAULT_MAX_TOKENS

    report = audit_pr(pr, fixed_output, judge_model=judge_model, api_keys=api_keys, max_tokens=max_tokens)
    baseline_output = generate_zero_shot_review(pr, baseline_model=baseline_model, api_keys=api_keys, max_tokens=max_tokens)
    baseline_rubric = score_rubric_only(pr, baseline_output, judge_model=judge_model, api_keys=api_keys, max_tokens=max_tokens)
    verdict, reasons = build_verdict(report)

    metrics = report.as_dict()
    metrics["baseline_rubric"] = baseline_rubric.as_dict()
    metrics["rubric_delta_vs_baseline"] = _rubric_delta(report.rubric, baseline_rubric)
    metrics["verdict"] = verdict
    metrics["verdict_reasons"] = reasons
    metrics["category_status"] = {cat: getattr(report, cat).status for cat in CATEGORIES}

    return {
        "benchmark": "eval_PR-single-pr-audit",
        "agent": "full_pipeline",
        "n": 1,
        "metrics": metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_placeholder": not (report.is_real and baseline_rubric.is_real),
    }


def render_markdown(result: dict, pr_label: str = "PR") -> str:
    m = result["metrics"]
    lines = [
        f"# eval_PR Audit Report — {pr_label}",
        "",
        f"_Generated {result['timestamp']}_",
        "",
    ]
    if result.get("is_placeholder"):
        lines.append("> ⚠️ **Placeholder result** — no provider API key was available for the selected models, so this run used demo/placeholder responses instead of a real audit.")
        lines.append("")

    lines.append(f"## Verdict: {'✅ GO' if m['verdict'] == 'GO' else '❌ NO-GO'}")
    lines.append("")
    if m["verdict_reasons"]:
        lines.append("**Reasons:**")
        for r in m["verdict_reasons"]:
            lines.append(f"- {r}")
        lines.append("")

    lines.append("## Categorical findings")
    for cat in CATEGORIES:
        c = m[cat]
        status_icon = {"resolved": "✅", "unresolved": "❌", "none_found": "⚪"}[m["category_status"][cat]]
        lines.append(f"### {cat.capitalize()} {status_icon} ({m['category_status'][cat]})")
        lines.append(f"- **Identified:** {', '.join(c['identified']) or '(none)'}")
        lines.append(f"- **Patched:** {', '.join(c['patched']) or '(none)'}")
        lines.append(f"- **Remaining:** {', '.join(c['remaining']) or '(none)'}")
        lines.append("")

    lines.append("## Quality rubric — this system vs. a zero-shot baseline")
    lines.append("| Dimension | System | Baseline | Delta |")
    lines.append("|---|---|---|---|")
    rubric, baseline, delta = m["rubric"], m["baseline_rubric"], m.get("rubric_delta_vs_baseline")
    for dim in ("coverage", "noise", "actionability", "coherence", "overall"):
        d = delta[dim] if delta else "—"
        lines.append(f"| {dim} | {rubric.get(dim, '—')} | {baseline.get(dim, '—')} | {d} |")
    if not delta:
        lines.append("")
        lines.append("_(Delta not shown — one or both rubric scores are still placeholders.)_")
    lines.append("")
    lines.append("The baseline never affects the verdict — it's shown only as evidence of what a")
    lines.append("multi-agent architecture adds over a single plain LLM call on this PR.")
    lines.append("")

    lines.append("## Adversarial resistance (4 attack categories)")
    rate = m["resistance_rate"]
    lines.append(f"**Resistance rate:** {rate if rate is not None else 'N/A — no attack pattern detected in this PR'}")
    lines.append("")
    lines.append("| Attack category | Detected | Resisted | Rationale |")
    lines.append("|---|---|---|---|")
    for attack in ATTACK_CATEGORIES:
        a = m["adversarial"][attack]
        lines.append(f"| {attack} | {a['detected']} | {a['resisted']} | {a['rationale']} |")
    lines.append("")
    lines.append(f"**Fixed Code itself still adversarial:** {m['fixed_output_contains_adversarial_content']}")
    if m.get("fixed_output_adversarial_rationale"):
        lines.append(f"  - {m['fixed_output_adversarial_rationale']}")
    lines.append("")

    lines.append("## Summary")
    lines.append(m.get("summary_rationale") or "(not provided)")

    return "\n".join(lines)


def _read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{path} not found")
    return p.read_text()


def run_from_files(pr_path: str, fixed_output_path: str, output_dir: str = "eval_pr_results") -> dict:
    """CLI-facing wrapper: reads two files, runs audit(), writes JSON + MD
    reports to output_dir, prints a summary, and returns the result dict."""
    pr = _read(pr_path)
    fixed_output = _read(fixed_output_path)

    result = audit(pr, fixed_output)
    result["source"] = {"pr_path": pr_path, "fixed_output_path": fixed_output_path}

    if result["is_placeholder"]:
        print(
            "[eval_pr] PLACEHOLDER result — set a provider key (ANTHROPIC_API_KEY, DEEPSEEK_API_KEY/LLM_API_KEY, or OPENAI_API_KEY) to run a real audit. "
            "This run demonstrates the tool's output shape, not a real assessment."
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(pr_path).stem
    out_json = out_dir / f"{stem}_audit.json"
    out_md = out_dir / f"{stem}_audit.md"

    with open(out_json, "w") as f:
        json.dump(result, f, indent=2)
    with open(out_md, "w") as f:
        f.write(render_markdown(result, pr_label=pr_path))

    m = result["metrics"]
    print(f"[eval_pr] verdict: {m['verdict']}")
    for r in m["verdict_reasons"]:
        print(f"  - {r}")
    print(f"[eval_pr] wrote {out_json}")
    print(f"[eval_pr] wrote {out_md}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pr", required=True, help="path to a file containing the original PR")
    parser.add_argument("--fixed-output", required=True, help="path to a file containing the system's Fixed Code (agent findings + patch + test results)")
    parser.add_argument("--output-dir", default="eval_pr_results")
    args = parser.parse_args()

    run_from_files(pr_path=args.pr, fixed_output_path=args.fixed_output, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
