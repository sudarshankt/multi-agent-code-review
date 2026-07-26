"""Release gate: applies the go/no-go rule set declared in
eval/config.yaml's `release_gate` block to a completed evaluation run, and
prints a single PASS/FAIL verdict with a breakdown of why.

This closes a real gap: targets like "F1 > 0.40" tell you how one run
compares to a number, but say nothing about what COMBINATION of scores
means "ready to ship." This script is the answer — and the rules live in
config.yaml, declared before results exist, specifically so the bar can't
be unconsciously fit to whatever the first real run produces.

Layer A checks are CI-aware where a metric has a computed confidence
interval (see config.yaml's `ci_key` per rule): the gate checks the CI's
LOWER bound against the target, not the raw point estimate, so a single
lucky sample can't pass a metric that's really borderline. Metrics without
a CI yet (style agreement, patch pass rate) fall back to the point
estimate, and the gate says so explicitly rather than treating every
metric as equally rigorous. If a committed baseline exists (see
`--save-baseline` below), each CI-backed metric's new interval is also
checked for overlap against the baseline's — a non-overlapping drop is
flagged as a real regression, not sampling noise.

Reads:
  - results/final_report.json           (Layer A, from aggregate_results.py)
  - eval/baseline/final_report.json      (optional — a trusted prior run, for
    regression detection; SKIPPED, not silently passed, if it doesn't exist)
  - results/full_pipeline__llm-judge-e2e.json   (Layer B, from run_e2e_review.py)
  - results/full_pipeline__adversarial-injection.json (from run_adversarial_eval.py)
  - results/judge_calibration.json       (from calibrate_judge.py, optional but
    recommended — without it, Layer B's gate check is skipped with a warning,
    not silently assumed to pass)

Usage:
    python -m eval.report.release_gate
    python -m eval.report.release_gate --save-baseline   # after a trusted run, e.g. a release
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.common import REPO_ROOT, load_config


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _ci_overlaps(new_ci: dict, baseline_ci: dict) -> bool:
    """Two confidence intervals overlap if neither is entirely above or
    entirely below the other."""
    return not (new_ci["ci_low"] > baseline_ci["ci_high"] or new_ci["ci_high"] < baseline_ci["ci_low"])


def check_layer_a(results_dir: Path, cfg: dict) -> list[dict]:
    final_report = _load_json(results_dir / "final_report.json")
    checks = []
    if final_report is None:
        return [{"rule": "Layer A results present", "status": "FAIL", "detail": "final_report.json not found — run aggregate_results.py"}]

    records_by_key = {(r["agent"], r["benchmark"]): r for r in final_report.get("records", [])}
    thresholds = cfg["thresholds"]
    layer_a_cfg = cfg["release_gate"]["layer_a"]

    baseline_path = REPO_ROOT / layer_a_cfg.get("baseline_path", "")
    baseline_report = _load_json(baseline_path) if layer_a_cfg.get("baseline_path") else None
    baseline_records = {(r["agent"], r["benchmark"]): r for r in baseline_report.get("records", [])} if baseline_report else {}

    for rule in layer_a_cfg["required_metrics"]:
        benchmark = rule["benchmark"]
        metric = rule["metric"]
        ci_key = rule.get("ci_key")
        target = thresholds.get(rule["threshold_key"])
        # startswith, not ==: --shared runs write "SecCodePLT-shared" / "BugsInPy-shared"
        # (see run_security_eval.py / run_bug_eval.py) so the gate rule still matches
        # regardless of which sampling mode produced the result.
        match = next((r for k, r in records_by_key.items() if r["benchmark"].startswith(benchmark)), None)

        if match is None:
            checks.append({
                "rule": f"{benchmark}.{metric} >= {target}",
                "status": "FAIL",
                "detail": f"no result found for benchmark '{benchmark}' — has it been run?",
            })
            continue

        metrics = match.get("metrics", {})
        actual = metrics.get(metric)
        if actual is None:
            checks.append({
                "rule": f"{benchmark}.{metric} >= {target}",
                "status": "FAIL",
                "detail": f"metric '{metric}' not present in {benchmark}'s result",
            })
            continue

        ci = metrics.get(ci_key) if ci_key else None
        if ci and "ci_low" in ci:
            # Gate on the CI's LOWER bound, not the point estimate — a
            # single lucky sample shouldn't be enough to pass a metric
            # that's genuinely borderline.
            checked_value = ci["ci_low"]
            status = "PASS" if checked_value >= target else "FAIL"
            checks.append({
                "rule": f"{benchmark}.{metric} 95% CI lower bound >= {target}",
                "status": status,
                "detail": f"point estimate = {actual}, CI = [{ci['ci_low']}, {ci['ci_high']}], checked value (lower bound) = {checked_value}",
            })
        else:
            status = "PASS" if actual >= target else "FAIL"
            checks.append({
                "rule": f"{benchmark}.{metric} >= {target}",
                "status": status,
                "detail": f"actual = {actual} (point estimate only — no CI computed for this metric yet, so this check is less robust to sampling noise than the CI-backed ones above)",
            })

        # Baseline regression check, only meaningful for CI-backed metrics.
        if ci_key:
            if baseline_report is None:
                checks.append({
                    "rule": f"{benchmark}.{metric} CI overlaps committed baseline",
                    "status": "SKIPPED",
                    "detail": f"no baseline found at {layer_a_cfg.get('baseline_path')} — commit a trusted run's final_report.json there to enable regression detection",
                })
            else:
                baseline_match = next((r for k, r in baseline_records.items() if r["benchmark"].startswith(benchmark)), None)
                baseline_ci = baseline_match.get("metrics", {}).get(ci_key) if baseline_match else None
                if not (ci and baseline_ci and "ci_low" in ci and "ci_low" in baseline_ci):
                    checks.append({
                        "rule": f"{benchmark}.{metric} CI overlaps committed baseline",
                        "status": "SKIPPED",
                        "detail": "baseline exists but has no comparable CI for this metric",
                    })
                else:
                    overlaps = _ci_overlaps(ci, baseline_ci)
                    status = "PASS" if overlaps else "FAIL"
                    detail = (
                        f"new CI = [{ci['ci_low']}, {ci['ci_high']}], baseline CI = [{baseline_ci['ci_low']}, {baseline_ci['ci_high']}]"
                        + ("" if overlaps else " — non-overlapping drop, this looks like a real regression, not sampling noise")
                    )
                    checks.append({"rule": f"{benchmark}.{metric} CI overlaps committed baseline", "status": status, "detail": detail})

    return checks


def check_layer_b(results_dir: Path, cfg: dict) -> list[dict]:
    e2e = _load_json(results_dir / "full_pipeline__llm-judge-e2e.json")
    calibration = _load_json(results_dir / "judge_calibration.json")
    rules = cfg["release_gate"]["layer_b"]
    checks = []

    if e2e is None:
        return [{"rule": "Layer B results present", "status": "FAIL", "detail": "full_pipeline__llm-judge-e2e.json not found — run run_e2e_review.py"}]

    metrics = e2e.get("metrics", {})

    positive_overall = metrics.get("positive_cases", {}).get("overall_mean")
    threshold = rules["min_positive_overall_mean"]
    if positive_overall is None:
        checks.append({"rule": f"positive_cases.overall_mean >= {threshold}", "status": "FAIL", "detail": "no positive-case scores found"})
    else:
        status = "PASS" if positive_overall >= threshold else "FAIL"
        checks.append({"rule": f"positive_cases.overall_mean >= {threshold}", "status": status, "detail": f"actual = {positive_overall}"})

    clean_coverage = metrics.get("clean_cases_false_positive_check", {}).get("coverage_mean")
    threshold = rules["min_clean_coverage_mean"]
    if clean_coverage is None:
        checks.append({"rule": f"clean_cases.coverage_mean >= {threshold}", "status": "FAIL", "detail": "no clean-case scores found"})
    else:
        status = "PASS" if clean_coverage >= threshold else "FAIL"
        checks.append({"rule": f"clean_cases.coverage_mean (false-positive avoidance) >= {threshold}", "status": status, "detail": f"actual = {clean_coverage}"})

    corr_threshold = rules["min_judge_human_correlation"]
    if calibration is None:
        checks.append({
            "rule": f"judge/human correlation >= {corr_threshold} (all dimensions)",
            "status": "SKIPPED",
            "detail": "judge_calibration.json not found — run calibrate_judge.py before trusting Layer B for a release decision",
        })
    else:
        untrusted = [dim for dim, res in calibration.items() if res.get("verdict") != "TRUST"]
        status = "PASS" if not untrusted else "FAIL"
        detail = "all dimensions trusted" if not untrusted else f"not yet trusted: {', '.join(untrusted)}"
        checks.append({"rule": f"judge/human correlation >= {corr_threshold} (all dimensions)", "status": status, "detail": detail})

    return checks


def check_adversarial(results_dir: Path, cfg: dict) -> list[dict]:
    adv = _load_json(results_dir / "full_pipeline__adversarial-injection.json")
    threshold = cfg["release_gate"]["adversarial"]["min_resistance_rate"]

    if adv is None:
        return [{"rule": f"adversarial resistance_rate >= {threshold}", "status": "FAIL", "detail": "full_pipeline__adversarial-injection.json not found — run run_adversarial_eval.py"}]

    rate = adv.get("metrics", {}).get("resistance_rate")
    if rate is None:
        return [{"rule": f"adversarial resistance_rate >= {threshold}", "status": "FAIL", "detail": "no resistance_rate in adversarial results"}]

    status = "PASS" if rate >= threshold else "FAIL"
    detail = f"actual = {rate}"
    if status == "FAIL":
        detail += " — ANY manipulated case blocks release; this is a security bug, not a quality average"
    return [{"rule": f"adversarial resistance_rate >= {threshold}", "status": status, "detail": detail}]


def save_as_baseline(results_dir: Path, cfg: dict) -> Path | None:
    """Copies the current final_report.json to the committed baseline
    path, for future runs' regression checks to compare against. Only
    call this after a run you trust — e.g. right after a release ships —
    since every future CI run will be compared against whatever's saved
    here."""
    final_report = _load_json(results_dir / "final_report.json")
    if final_report is None:
        print("[release_gate] no final_report.json to save — run aggregate_results.py first.")
        return None

    baseline_path = REPO_ROOT / cfg["release_gate"]["layer_a"]["baseline_path"]
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "w") as f:
        json.dump(final_report, f, indent=2)
    print(f"[release_gate] saved current results as the new baseline: {baseline_path}")
    print("[release_gate] commit this file — future runs will be compared against it.")
    return baseline_path


def run_gate(results_dir: Path | None = None) -> dict:
    cfg = load_config()
    results_dir = results_dir or REPO_ROOT / cfg["paths"]["results_dir"]

    all_checks = (
        [("Layer A", c) for c in check_layer_a(results_dir, cfg)]
        + [("Layer B", c) for c in check_layer_b(results_dir, cfg)]
        + [("Adversarial", c) for c in check_adversarial(results_dir, cfg)]
    )

    print(f"\n{'Section':<14} {'Status':<9} Rule")
    print("-" * 90)
    for section, check in all_checks:
        print(f"{section:<14} {check['status']:<9} {check['rule']}")
        print(f"{'':<14} {'':<9} {check['detail']}")

    n_fail = sum(1 for _, c in all_checks if c["status"] == "FAIL")
    n_skipped = sum(1 for _, c in all_checks if c["status"] == "SKIPPED")
    overall = "FAIL" if n_fail > 0 else ("INCOMPLETE" if n_skipped > 0 else "PASS")

    print("-" * 90)
    print(f"OVERALL: {overall}  ({n_fail} failed, {n_skipped} skipped, "
          f"{len(all_checks) - n_fail - n_skipped} passed of {len(all_checks)})\n")

    result = {"overall": overall, "checks": [{"section": s, **c} for s, c in all_checks]}
    out_path = results_dir / "release_gate.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[release_gate] wrote {out_path}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save-baseline", action="store_true",
        help="save the current final_report.json as the committed baseline for future regression checks, instead of running the gate",
    )
    args = parser.parse_args()

    if args.save_baseline:
        cfg = load_config()
        results_dir = REPO_ROOT / cfg["paths"]["results_dir"]
        save_as_baseline(results_dir, cfg)
    else:
        run_gate()
