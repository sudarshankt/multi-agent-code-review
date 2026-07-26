"""Build a small, curated set of real PR-shaped test cases with known
ground truth, reusing the same BugsInPy/SecCodePLT data the per-agent
runners already use — but here each case is a whole PR, scored as a whole,
not reduced to a single 0/1 label.

Includes both POSITIVE cases (the PR contains a real, known bug/vuln) and
NEGATIVE/clean cases (the PR is the already-fixed, working version — the
correct system output is an empty or near-empty report). Negative cases
close a real gap: without them, a system that flags something on every PR
would score fine on positive-only cases. Built from SecCodePLT's
`patched_code` side (BugsInPy only ships a diff, not full pre/post file
text, so it can't cheaply produce a negative case the same way — see
Evaluation_Harness_Spec.md's Known Limitations for that gap).

Each case:
{
  "case_id": str,
  "source_benchmark": "bugsinpy" | "seccodeplt",
  "is_clean": bool,           # True = negative case, no real issue present
  "pr_diff": str,             # the incoming code, PR-shaped
  "known_issue": {            # None when is_clean=True
      "type": "bug" | "vulnerability",
      "description": str,
      "cwe_id": str | None,
  } | None,
  "ground_truth_fix": str,    # for positive cases: the real patch/fix.
                               # for negative cases: same as pr_diff (already clean)
  "metadata": {...}
}

Usage:
    python -m eval.e2e.build_pr_cases --n 20
"""
from __future__ import annotations

import argparse
import json

from eval.common import REPO_ROOT, load_config


def _format_diff_header(filename: str) -> str:
    return f"--- a/{filename}\n+++ b/{filename}\n"


def build_from_bugsinpy(n: int, shared_case_ids: list[str] | None = None) -> list[dict]:
    from eval.datasets.download_bugsinpy import load_sample

    if shared_case_ids is not None:
        bugs = load_sample(case_ids=shared_case_ids)
    else:
        bugs = load_sample(sample_n=n)
    cases = []
    for bug in bugs:
        patch = bug.get("patch", "")
        if not patch:
            continue
        already_has_header = patch.strip().startswith("diff --git")
        pr_diff = patch if already_has_header else _format_diff_header(bug.get("test_file", "unknown.py")) + patch
        cases.append({
            "case_id": f"bugsinpy-{bug['project']}-{bug['bug_id']}",
            "source_benchmark": "bugsinpy",
            "is_clean": False,
            "pr_diff": pr_diff,
            "known_issue": {
                "type": "bug",
                "description": f"Real bug in {bug['project']} (bug #{bug['bug_id']}), "
                                f"fixed at commit {bug.get('fixed_commit_id', '')[:10]}",
                "cwe_id": None,
            },
            "ground_truth_fix": patch,
            "metadata": {"project": bug["project"], "bug_id": bug["bug_id"]},
        })
    return cases


def build_from_seccodeplt(n: int, include_clean: bool = True, shared_indices: list[int] | None = None) -> tuple[list[dict], list[dict]]:
    """Returns (positive_cases, clean_cases). Each SecCodePLT sample gives
    a real vulnerable/patched pair — the vulnerable side becomes a
    positive case, the already-patched side becomes a negative/clean case
    (same function, same CWE context, but the fix is already applied — the
    correct system output is an empty or near-empty report).
    """
    from eval.datasets.download_seccodeplt import load_samples

    if shared_indices is not None:
        samples = load_samples(indices=shared_indices)
    else:
        samples = load_samples(sample_n=n)
    positive_cases, clean_cases = [], []
    for ex in samples:
        gt = ex.get("ground_truth", {})
        code_before = gt.get("code_before", "")
        vulnerable = code_before + gt.get("vulnerable_code", "")
        patched = code_before + gt.get("patched_code", "")
        if not vulnerable:
            continue
        func_name = ex.get("task_description", {}).get("function_name", "unknown")
        idx = ex.get("index", func_name)

        positive_cases.append({
            "case_id": f"seccodeplt-{idx}",
            "source_benchmark": "seccodeplt",
            "is_clean": False,
            "pr_diff": _format_diff_header(f"{func_name}.py") + vulnerable,
            "known_issue": {
                "type": "vulnerability",
                "description": ex.get("task_description", {}).get("security_policy", ""),
                "cwe_id": f"CWE-{ex.get('CWE_ID', '')}",
            },
            "ground_truth_fix": patched,
            "metadata": {"function_name": func_name},
        })

        if include_clean and patched:
            clean_cases.append({
                "case_id": f"seccodeplt-{idx}-clean",
                "source_benchmark": "seccodeplt",
                "is_clean": True,
                "pr_diff": _format_diff_header(f"{func_name}.py") + patched,
                "known_issue": None,
                "ground_truth_fix": patched,
                "metadata": {"function_name": func_name, "paired_with": f"seccodeplt-{idx}"},
            })
    return positive_cases, clean_cases


def build(n_per_source: int = 10, use_shared: bool = False) -> list[dict]:
    cfg = load_config()
    cases = []

    shared_bugsinpy_ids, shared_seccodeplt_indices = None, None
    if use_shared:
        from eval.shared_cases import load_registry
        registry = load_registry()
        shared_bugsinpy_ids = registry["bugsinpy_case_ids"]
        shared_seccodeplt_indices = registry["seccodeplt_indices"]

    try:
        cases += build_from_bugsinpy(n_per_source, shared_case_ids=shared_bugsinpy_ids)
    except FileNotFoundError:
        print("[e2e/build_cases] BugsInPy not downloaded — skipping. Run "
              "`python -m eval.datasets.download_bugsinpy` first.")
    try:
        positive, clean = build_from_seccodeplt(n_per_source, shared_indices=shared_seccodeplt_indices)
        cases += positive + clean
    except FileNotFoundError:
        print("[e2e/build_cases] SecCodePLT not downloaded — skipping. Run "
              "`python -m eval.datasets.download_seccodeplt` first.")

    out_path = REPO_ROOT / cfg["paths"]["dataset_dir"] / "e2e_cases.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")

    n_clean = sum(1 for c in cases if c.get("is_clean"))
    print(f"[e2e/build_cases] wrote {len(cases)} PR cases to {out_path} "
          f"({len(cases) - n_clean} positive, {n_clean} clean/negative)")
    return cases


def load_cases(sample_n: int | None = None) -> list[dict]:
    cfg = load_config()
    path = REPO_ROOT / cfg["paths"]["dataset_dir"] / "e2e_cases.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python -m eval.e2e.build_pr_cases` first.")
    cases = []
    with open(path) as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
    if sample_n is not None and sample_n < len(cases):
        cases = cases[:sample_n]
    return cases


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=cfg["sample_sizes"].get("e2e_cases_per_source", 10),
                         help="cases per source benchmark (ignored if --shared)")
    parser.add_argument("--shared", action="store_true",
                         help="build cases from the fixed eval.shared_cases registry instead, "
                              "enabling per-case comparison against Layer A's --shared results")
    args = parser.parse_args()
    build(args.n, use_shared=args.shared)
