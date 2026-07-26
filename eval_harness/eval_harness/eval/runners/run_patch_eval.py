"""Patch Generation Agent evaluation runner.

Benchmarks:
  - PatchEval, Python subset (Wei et al., arXiv:2511.11019) — 404 real
    Python CVEs, filtered from the multilingual 1,000-CVE set.
  - BugsInPy patch pass rate — reuses the Bug Agent's BugsInPy data with
    its real failing->passing test harness, a non-CVE complement to
    PatchEval's security-focused patches.

Usage:
    python -m eval.runners.run_patch_eval --benchmark patcheval
    python -m eval.runners.run_patch_eval --benchmark bugsinpy
"""
from __future__ import annotations

import argparse
import difflib

from eval.agent_interface import generate_patch
from eval.common import load_config, write_result
from eval.metrics.classification import PatchEvalResult, patch_pass_rate


def _touches_test_files(original: str, patched: str, filename: str) -> bool:
    """Flag patches that modify test files themselves — a red flag that
    the 'fix' just weakened/deleted the failing test."""
    if "test" not in filename.lower():
        return False
    diff = list(difflib.unified_diff(original.splitlines(), patched.splitlines()))
    return len(diff) > 0


def run_patcheval(n: int | None = None) -> dict:
    """Only 230/1000 CVEs (across all languages) have Docker-sandbox
    PoC+functional-test verification. This runner uses a placeholder
    "changed the code at all" pass criterion — replace with PatchEval's
    own evaluator (patcheval/evaluation/) once the Docker sandbox is set up.
    """
    from eval.datasets.download_patcheval import load_python_subset

    cfg = load_config()
    n = n or cfg["sample_sizes"]["patcheval_python_n"]

    try:
        examples = load_python_subset(sample_n=n)
    except FileNotFoundError:
        print(
            "[patch/patcheval] dataset not downloaded. Run "
            "`python -m eval.datasets.download_patcheval` first."
        )
        return {}

    results = []
    for ex in examples:
        vul_funcs = ex.get("vul_func", [])
        if not vul_funcs:
            continue
        snippet = vul_funcs[0].get("snippet", "")
        file_path = vul_funcs[0].get("file_path", "")
        description = ex.get("cve_description", "")

        patched = generate_patch(snippet, description)
        tampered = _touches_test_files(snippet, patched, file_path)
        passed = patched != snippet and not tampered
        results.append(PatchEvalResult(passed=passed, tampered_tests=tampered))

    rates = patch_pass_rate(results)
    target = cfg["thresholds"]["patcheval_python_patch_success_target"]
    rates["meets_target"] = rates["clean_pass_rate"] >= target
    rates["target"] = target
    rates["caveat"] = "placeholder pass criterion — needs PatchEval's Docker-sandbox evaluator for real verification"

    out = write_result(benchmark="PatchEval-python", agent="patch_generation", n=len(examples), metrics=rates)
    print(f"[patch/patcheval] wrote {out}  clean_pass_rate={rates['clean_pass_rate']}  (target {target})")
    return rates


def run_bugsinpy_patch(n: int | None = None) -> dict:
    """Requires Docker + BugsInPy's CLI (bugsinpy-checkout, bugsinpy-test)
    for the actual test-pass check; without Docker this only validates
    that a patch was generated, not that it passes the real test suite.
    """
    from eval.datasets.download_bugsinpy import load_sample

    cfg = load_config()
    n = n or cfg["sample_sizes"]["bugsinpy_n"]

    try:
        bugs = load_sample(sample_n=n)
    except FileNotFoundError:
        print(
            "[patch/bugsinpy] dataset not downloaded. Run "
            "`python -m eval.datasets.download_bugsinpy` first."
        )
        return {}

    results = []
    for bug in bugs:
        patch = bug.get("patch", "")
        test_file = bug.get("test_file", "")
        if not patch:
            continue
        generated = generate_patch(patch, f"Fix bug in {bug.get('project')}")
        tampered = _touches_test_files(patch, generated, test_file)
        passed = generated != patch and not tampered
        results.append(PatchEvalResult(passed=passed, tampered_tests=tampered))

    rates = patch_pass_rate(results)
    target = cfg["thresholds"]["bugsinpy_patch_pass_target"]
    rates["meets_target"] = rates["clean_pass_rate"] >= target
    rates["target"] = target
    rates["caveat"] = "placeholder pass criterion — needs real bugsinpy-test run via Docker for true verification"

    out = write_result(benchmark="BugsInPy-patch", agent="patch_generation", n=len(results), metrics=rates)
    print(f"[patch/bugsinpy] wrote {out}  clean_pass_rate={rates['clean_pass_rate']}  (target {target})")
    return rates


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=["patcheval", "bugsinpy", "all"], default="all")
    parser.add_argument("--n", type=int, default=None)
    args = parser.parse_args()

    if args.benchmark in ("patcheval", "all"):
        run_patcheval(args.n)
    if args.benchmark in ("bugsinpy", "all"):
        run_bugsinpy_patch(args.n)
