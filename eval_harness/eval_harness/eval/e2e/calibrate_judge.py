"""Compare the LLM judge's scores against human-scored rubric CSVs, per
dimension, and apply a DEFINED trust threshold — closing the gap where
"calibrate the judge against humans" had no stated bar for what counts as
good enough.

Usage:
    # after filling in eval/e2e/human_rubric_sample.csv by hand:
    python -m eval.e2e.calibrate_judge

Threshold rule (Pearson correlation r, per dimension, computed across the
cases that have both a judge score and a filled-in human score):
    r >= 0.6   -> TRUST:      use the judge alone at scale for this dimension
    0.4 <= r < 0.6 -> REVIEW: judge is directionally useful but should be
                     spot-checked; consider a larger human sample before
                     relying on it for merge-blocking decisions
    r < 0.4    -> DO NOT TRUST: the judge disagrees with humans too often on
                     this dimension. Try a different judge model, tighten
                     the rubric definitions in llm_judge.py's prompt, or
                     keep this dimension human-only for now.

This is a starting threshold, not a universal constant — tighten it if
the cost of a false "trust" is high (e.g., this gates auto-merge).
"""
from __future__ import annotations

import argparse
import csv
import json

from eval.common import REPO_ROOT

DIMENSIONS = ["coverage", "noise", "actionability", "coherence", "overall"]

TRUST_THRESHOLD = 0.6
REVIEW_THRESHOLD = 0.4


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None  # not enough paired data points to trust a correlation
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None  # no variance in one side — correlation undefined
    return cov / (var_x * var_y) ** 0.5


def _load_human_scores(csv_path) -> dict[str, dict]:
    scores = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            vals = {}
            for dim in DIMENSIONS:
                raw = row.get(f"{dim}_1to5", "").strip()
                if raw:
                    try:
                        vals[dim] = int(raw)
                    except ValueError:
                        pass
            if vals:
                scores[row["case_id"]] = vals
    return scores


def _load_judge_scores(results_dir) -> dict[str, dict]:
    path = results_dir / "full_pipeline__llm-judge-e2e.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m eval.e2e.run_e2e_review` first."
        )
    with open(path) as f:
        record = json.load(f)
    per_case = record.get("extra", {}).get("per_case_scores", [])
    return {s["case_id"]: s for s in per_case if not s.get("parse_error")}


def calibrate(
    human_csv_path=None,
    results_dir=None,
) -> dict:
    from eval.common import load_config

    cfg = load_config()
    human_csv_path = human_csv_path or (REPO_ROOT / "eval" / "e2e" / "human_rubric_sample.csv")
    results_dir = results_dir or (REPO_ROOT / cfg["paths"]["results_dir"])

    if not human_csv_path.exists():
        print(
            f"[calibrate] {human_csv_path} not found or not filled in yet. "
            "Run run_e2e_review.py first, then score the CSV by hand."
        )
        return {}

    human_scores = _load_human_scores(human_csv_path)
    if not human_scores:
        print(
            f"[calibrate] {human_csv_path} has no filled-in scores yet — "
            "nothing to calibrate against."
        )
        return {}

    judge_scores = _load_judge_scores(results_dir)

    report = {}
    for dim in DIMENSIONS:
        paired_human, paired_judge = [], []
        for case_id, h in human_scores.items():
            if dim in h and case_id in judge_scores and dim in judge_scores[case_id]:
                paired_human.append(h[dim])
                paired_judge.append(judge_scores[case_id][dim])

        r = _pearson(paired_human, paired_judge)
        if r is None:
            verdict = "INSUFFICIENT_DATA"
        elif r >= TRUST_THRESHOLD:
            verdict = "TRUST"
        elif r >= REVIEW_THRESHOLD:
            verdict = "REVIEW"
        else:
            verdict = "DO_NOT_TRUST"

        report[dim] = {
            "n_paired": len(paired_human),
            "pearson_r": round(r, 3) if r is not None else None,
            "verdict": verdict,
        }

    print(f"\n{'Dimension':<15} {'n':>4} {'r':>7}  Verdict")
    print("-" * 45)
    for dim, res in report.items():
        r_str = f"{res['pearson_r']:.3f}" if res["pearson_r"] is not None else "  n/a"
        print(f"{dim:<15} {res['n_paired']:>4} {r_str:>7}  {res['verdict']}")
    print(
        f"\nThresholds: r>={TRUST_THRESHOLD} TRUST | "
        f"{REVIEW_THRESHOLD}<=r<{TRUST_THRESHOLD} REVIEW | r<{REVIEW_THRESHOLD} DO_NOT_TRUST\n"
    )

    out_path = results_dir / "judge_calibration.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[calibrate] wrote {out_path}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    calibrate()
