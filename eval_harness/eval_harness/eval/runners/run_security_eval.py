"""Security Agent evaluation runner.

Benchmark: SecCodePLT (Nie et al., arXiv:2410.11096, NeurIPS 2025) —
Python-native, 1,411 samples, 28 CWEs. Ships directly in its git repo,
verified against the live data.

Usage:
    python -m eval.runners.run_security_eval
    python -m eval.runners.run_security_eval --n 50
    python -m eval.runners.run_security_eval --shared   # scores the fixed
        registry from eval.shared_cases, enabling per-case comparison
        against Layer B/C's results for the same underlying examples
"""
from __future__ import annotations

import argparse

from eval.agent_interface import predict_vulnerability, zero_shot_llm_call
from eval.common import load_config, write_result
from eval.metrics.classification import precision_recall_f1
from eval.metrics.stats import bootstrap_ci


def run_seccodeplt(n: int | None = None, use_shared: bool = False) -> dict:
    """Builds a balanced binary task from each sample's vulnerable_code vs.
    patched_code pair, since SecCodePLT ships paired examples rather than
    pre-labeled 0/1 rows.

    Records per-example predictions in the result's `extra.per_example`
    field, keyed by the same case_id format eval.e2e uses
    ("seccodeplt-{index}" / "seccodeplt-{index}-clean") — this is what
    makes cross-layer comparison possible; without it there'd be no way
    to join a Layer A score back to a specific Layer B/C case.
    """
    from eval.datasets.download_seccodeplt import load_samples

    cfg = load_config()

    if use_shared:
        from eval.shared_cases import load_registry
        registry = load_registry()
        samples = load_samples(indices=registry["seccodeplt_indices"])
    else:
        n = n or cfg["sample_sizes"]["seccodeplt_n"]
        try:
            samples = load_samples(sample_n=n)
        except FileNotFoundError:
            print(
                "[security/seccodeplt] dataset not downloaded. Run "
                "`python -m eval.datasets.download_seccodeplt` first."
            )
            return {}

    y_true, y_pred, zs_pred = [], [], []
    per_example = []
    for ex in samples:
        gt = ex.get("ground_truth", {})
        code_before = gt.get("code_before", "")
        vulnerable = code_before + gt.get("vulnerable_code", "")
        patched = code_before + gt.get("patched_code", "")
        idx = ex.get("index")

        pred_vuln = predict_vulnerability(vulnerable)
        pred_patched = predict_vulnerability(patched)
        y_true += [1, 0]
        y_pred += [pred_vuln, pred_patched]
        per_example.append({"case_id": f"seccodeplt-{idx}", "y_true": 1, "y_pred": pred_vuln, "correct": pred_vuln == 1})
        per_example.append({"case_id": f"seccodeplt-{idx}-clean", "y_true": 0, "y_pred": pred_patched, "correct": pred_patched == 0})

        for code, label in ((vulnerable, 1), (patched, 0)):
            resp = zero_shot_llm_call(f"Is this Python code vulnerable?\n{code}")
            zs_pred.append(1 if "vulnerable" in resp.lower() else 0)

    prf1 = precision_recall_f1(y_true, y_pred)
    per_example_correct = [1.0 if t == p else 0.0 for t, p in zip(y_true, y_pred)]
    ci = bootstrap_ci(per_example_correct)
    zs_prf1 = precision_recall_f1(y_true, zs_pred)

    metrics = prf1.as_dict()
    metrics["accuracy_ci95"] = ci
    target = cfg["thresholds"]["seccodeplt_target"]
    metrics["meets_target"] = metrics["f1"] >= target
    metrics["target"] = target

    path = write_result(
        benchmark="SecCodePLT" + ("-shared" if use_shared else ""),
        agent="security",
        n=len(y_true),
        metrics=metrics,
        baseline_zero_shot=zs_prf1.as_dict(),
        extra={"per_example": per_example},
    )
    print(f"[security/seccodeplt] wrote {path}  F1={metrics['f1']}  (target {target})")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--shared", action="store_true", help="score the fixed shared-case registry instead of --n samples")
    args = parser.parse_args()
    run_seccodeplt(args.n, use_shared=args.shared)
