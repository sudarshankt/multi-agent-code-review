"""Style & Performance Agent evaluation runner.

Benchmarks (Section 2):
  - Pylint agreement (from proposal, target >90%)
  - Radon complexity ground-truth spot-check (added)

Both are self-baselines run directly against the same file set — no
external dataset download needed, which is exactly why they were flagged
in Section 2 as "no public style-correctness benchmark exists."

Usage:
    python -m eval.runners.run_style_eval --files path/to/*.py
"""
from __future__ import annotations

import argparse
import glob
import json
import subprocess

from eval.agent_interface import style_flags
from eval.common import load_config, write_result
from eval.metrics.classification import pep8_agreement


def _run_pylint(filepath: str) -> set[tuple]:
    """Run Pylint on a file and return {(line, rule_id), ...}."""
    result = subprocess.run(
        ["pylint", "--output-format=json", filepath],
        capture_output=True,
        text=True,
    )
    try:
        issues = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        issues = []
    return {(issue["line"], issue["message-id"]) for issue in issues}


def _run_radon(filepath: str) -> dict:
    """Run Radon cyclomatic complexity on a file, return {function: score}."""
    result = subprocess.run(
        ["radon", "cc", "-j", filepath], capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    scores = {}
    for block in data.get(filepath, []):
        scores[block["name"]] = block["complexity"]
    return scores


def run_pylint_agreement(files: list[str]) -> dict:
    cfg = load_config()
    all_agent_flags: set = set()
    all_pylint_flags: set = set()

    for f in files:
        pylint_flags = {(f, line, rule) for line, rule in _run_pylint(f)}
        agent_flags = {(f, line, rule) for line, rule in style_flags(open(f).read())}
        all_pylint_flags |= pylint_flags
        all_agent_flags |= agent_flags

    metrics = pep8_agreement(all_agent_flags, all_pylint_flags)
    target = cfg["thresholds"]["pep8_agreement_target"]
    metrics["target"] = target
    metrics["meets_target"] = (metrics.get("agreement") or 0) >= target

    out = write_result(benchmark="Pylint-agreement", agent="style", n=len(files), metrics=metrics)
    print(f"[style/pylint] wrote {out}  agreement={metrics.get('agreement')}  (target {target})")
    return metrics


def run_radon_spot_check(files: list[str]) -> dict:
    """Compares agent-reported complexity (via agent_interface — TODO: add
    a predict_complexity() stub there once the Style Agent exposes one) to
    Radon's own computed values. Currently just reports Radon's numbers,
    since the agent-side complexity-reporting hook isn't defined yet in
    agent_interface.py — add it there and diff against this."""
    all_scores = {}
    for f in files:
        all_scores[f] = _run_radon(f)

    n_functions = sum(len(v) for v in all_scores.values())
    metrics = {
        "n_files": len(files),
        "n_functions_scored": n_functions,
        "radon_scores": all_scores,
        "note": "agent-vs-radon diff not yet wired — see docstring",
    }
    out = write_result(benchmark="Radon-complexity", agent="style", n=n_functions, metrics=metrics)
    print(f"[style/radon] wrote {out}  ({n_functions} functions scored)")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", default=None, help="glob pattern(s), e.g. src/**/*.py")
    parser.add_argument("--benchmark", choices=["pylint", "radon", "all"], default="all")
    args = parser.parse_args()

    file_list = []
    for pattern in (args.files or ["eval/data/style_sample/**/*.py"]):
        file_list.extend(glob.glob(pattern, recursive=True))

    if not file_list:
        print("No files matched. Pass --files with a glob, e.g. --files 'src/**/*.py'")
    else:
        if args.benchmark in ("pylint", "all"):
            run_pylint_agreement(file_list)
        if args.benchmark in ("radon", "all"):
            run_radon_spot_check(file_list)
