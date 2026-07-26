"""Bug Detection Agent evaluation runner.

Benchmark: BugsInPy (Widyasari et al., ESEC/FSE 2020) — Python-native,
493 real bugs across 17 projects, Docker+CLI structured like Defects4J.
Verified against the live repo: github.com/soarsmu/BugsInPy.

Usage:
    python -m eval.runners.run_bug_eval
    python -m eval.runners.run_bug_eval --n 50
    python -m eval.runners.run_bug_eval --shared   # scores the fixed
        registry from eval.shared_cases, enabling per-case comparison
        against Layer B/C's results for the same underlying examples
"""
from __future__ import annotations

import argparse

from eval.agent_interface import predict_bug
from eval.common import load_config, write_result
from eval.metrics.classification import precision_recall_f1
from eval.metrics.stats import bootstrap_ci


def run_bugsinpy(n: int | None = None, use_shared: bool = False) -> dict:
    """Each bug gives a buggy_commit_id / fixed_commit_id pair. This
    runner reads the *patch* only, which is enough for a lightweight
    label-detection eval but not full repo-context evaluation — it's
    currently a recall-only proxy (every example is label=1) until a real
    pre-fix file checkout (via `bugsinpy-checkout`, needs Docker) is added
    to also produce label=0 (fixed-version) rows for true precision.

    Records per-example predictions in the result's `extra.per_example`
    field, keyed by "bugsinpy-{project}-{bug_id}" — the same case_id
    format eval.e2e.build_pr_cases uses, so Layer A's score on a specific
    bug can be joined against Layer B/C's score on the same bug.
    """
    from eval.datasets.download_bugsinpy import load_sample

    cfg = load_config()

    if use_shared:
        from eval.shared_cases import load_registry
        registry = load_registry()
        bugs = load_sample(case_ids=registry["bugsinpy_case_ids"])
    else:
        n = n or cfg["sample_sizes"]["bugsinpy_n"]
        try:
            bugs = load_sample(sample_n=n)
        except FileNotFoundError:
            print(
                "[bug/bugsinpy] dataset not downloaded. Run "
                "`python -m eval.datasets.download_bugsinpy` first."
            )
            return {}

    y_true, y_pred = [], []
    per_example = []
    for bug in bugs:
        patch = bug.get("patch", "")
        if not patch:
            continue
        pred = predict_bug(patch, repo_context=bug.get("project"))
        y_true += [1]
        y_pred += [pred]
        per_example.append({
            "case_id": f"bugsinpy-{bug['project']}-{bug['bug_id']}",
            "y_true": 1, "y_pred": pred, "correct": pred == 1,
        })

    if not y_true:
        print("[bug/bugsinpy] no bugs with patch data found in sample.")
        return {}

    prf1 = precision_recall_f1(y_true, y_pred)
    ci = bootstrap_ci([1.0 if p == 1 else 0.0 for p in y_pred])

    metrics = prf1.as_dict()
    metrics["recall_ci95"] = ci
    metrics["caveat"] = (
        "recall-only proxy — needs a real bugsinpy-checkout pre-fix/post-fix "
        "file diff (via Docker) for true precision"
    )
    target = cfg["thresholds"]["bugsinpy_detection_target"]
    metrics["meets_target"] = metrics["recall"] >= target
    metrics["target"] = target

    out = write_result(
        benchmark="BugsInPy" + ("-shared" if use_shared else ""),
        agent="bug_detection",
        n=len(y_true),
        metrics=metrics,
        extra={"per_example": per_example},
    )
    print(f"[bug/bugsinpy] wrote {out}  recall={metrics['recall']}  (target {target})")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--shared", action="store_true", help="score the fixed shared-case registry instead of --n samples")
    args = parser.parse_args()
    run_bugsinpy(args.n, use_shared=args.shared)
