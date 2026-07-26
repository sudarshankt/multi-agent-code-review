"""Cross-cutting zero-shot single-LLM ablation baseline (Section 2).

Runs the same test sets through one zero-shot LLM call (no LangGraph, no
RAG, no supervisor) so the final report can show the delta the multi-agent
+ RAG architecture actually adds over each per-agent metric.

Most runners (run_security_eval.py, etc.) already call
eval.agent_interface.zero_shot_llm_call inline and write it into their
own result's `baseline_zero_shot` field — this script is for running the
ablation as a standalone pass (e.g. to sanity-check it in isolation, or
re-run just the baseline without re-running the full agent eval).

Usage:
    python -m eval.runners.run_ablation_eval --benchmark primevul
"""
from __future__ import annotations

import argparse


def run_all_ablations(n: int | None = None) -> None:
    print(
        "[ablation] The zero-shot baseline is computed inline inside each "
        "runner (see run_security_eval.run_primevul for the pattern) and "
        "stored in that runner's `baseline_zero_shot` field. Run the "
        "per-agent runners with --benchmark all; aggregate_results.py will "
        "pull baseline_zero_shot out of each result automatically and "
        "compute the delta.\n"
        "This script is a placeholder for adding a standalone ablation "
        "pass later (e.g. testing prompt variants for the zero-shot "
        "baseline itself) — extend it if that becomes useful."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=None)
    args = parser.parse_args()
    run_all_ablations(args.n)
