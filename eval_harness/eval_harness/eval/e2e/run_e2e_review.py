"""End-to-end PR review quality runner.

Runs the FULL pipeline (agent_interface.run_full_pipeline — supervisor +
all agents together) against a curated set of real PR cases with known
ground truth, then scores each resulting final_report with an LLM judge.
Also writes a sample CSV for human rubric scoring, since the LLM judge
alone shouldn't be trusted without validating it against human judgment
first (see Section 3 of the E2E design in Evaluation_Harness_Spec.md).

Usage:
    python -m eval.e2e.build_pr_cases --n 10      # once, to build the case set
    python -m eval.e2e.run_e2e_review --n 20
"""
from __future__ import annotations

import argparse
import csv
from statistics import mean

from eval.agent_interface import run_full_pipeline
from eval.common import REPO_ROOT, Timer, load_config, write_result
from eval.e2e.build_pr_cases import load_cases
from eval.e2e.llm_judge import judge_batch


def run(n: int | None = None) -> dict:
    cfg = load_config()
    n = n if n is not None else cfg["sample_sizes"].get("e2e_review_n")

    try:
        cases = load_cases(sample_n=n)
    except FileNotFoundError as e:
        print(f"[e2e/review] {e}")
        return {}

    cases_with_reports = []
    pipeline_latencies = []
    for case in cases:
        with Timer() as t:
            final_report = run_full_pipeline(case["pr_diff"])
        pipeline_latencies.append(t.elapsed_seconds)
        cases_with_reports.append((case, final_report))

    latency_summary = Timer.summarize(pipeline_latencies)

    judge_scores = judge_batch(cases_with_reports)

    parsed_scores = [
        s for s in judge_scores
        if not s.get("parse_error") and s["overall"] > 0  # overall=0 means no API key configured or the call failed (see logs)
    ]
    n_parse_failures = len(judge_scores) - len(parsed_scores)

    positive_scores = [s for s in parsed_scores if not s.get("is_clean")]
    clean_scores = [s for s in parsed_scores if s.get("is_clean")]

    if not parsed_scores:
        print(
            f"[e2e/review] 0/{len(judge_scores)} judge calls returned real "
            "scores — set ANTHROPIC_API_KEY (see eval/llm_config.py) for a real judge, "
            "or check the logs above for an API error if a key is already configured."
        )
        summary = {"n": len(cases), "n_judged": 0, "n_parse_failures": n_parse_failures}
    else:
        def _dims(scores: list[dict]) -> dict:
            return {
                "coverage_mean": round(mean(s["coverage"] for s in scores), 2),
                "noise_mean": round(mean(s["noise"] for s in scores), 2),
                "actionability_mean": round(mean(s["actionability"] for s in scores), 2),
                "coherence_mean": round(mean(s["coherence"] for s in scores), 2),
                "overall_mean": round(mean(s["overall"] for s in scores), 2),
            }

        summary = {
            "n": len(cases),
            "n_judged": len(parsed_scores),
            "n_parse_failures": n_parse_failures,
            "n_positive_cases": len(positive_scores),
            "n_clean_cases": len(clean_scores),
        }
        if positive_scores:
            summary["positive_cases"] = _dims(positive_scores)  # detection quality
        if clean_scores:
            # "coverage" here means "correctly avoided a false positive" — see
            # llm_judge.CLEAN_PROMPT_TEMPLATE. Surfaced separately, never
            # averaged together with positive_cases' coverage — they measure
            # different things and blending them would hide a high
            # false-positive rate behind good detection, or vice versa.
            summary["clean_cases_false_positive_check"] = _dims(clean_scores)

    # Latency is reported regardless of judge status — it's measured on the
    # pipeline call itself, not the judge, so it's real even before the
    # judge is wired up. Addresses the "no latency/cost metrics" gap.
    summary["pipeline_latency"] = latency_summary

    out = write_result(
        benchmark="LLM-judge-e2e",
        agent="full_pipeline",
        n=len(cases),
        metrics=summary,
        extra={"per_case_scores": judge_scores},
    )
    print(f"[e2e/review] wrote {out}  n={len(cases)}  judged={summary.get('n_judged', 0)}")

    _write_human_rubric_sample(cases_with_reports)
    return summary


def _write_human_rubric_sample(cases_with_reports: list[tuple[dict, dict]]) -> None:
    """A held-out human-scoring sample — should be run on a SUBSET distinct
    from (or overlapping, for calibration) what the LLM judge scored, so
    you can check the judge's scores actually correlate with a human's
    before trusting it at scale.
    """
    out_path = REPO_ROOT / "eval" / "e2e" / "human_rubric_sample.csv"
    fieldnames = [
        "case_id", "is_clean", "pr_diff_excerpt", "known_issue_description", "final_report_summary",
        "coverage_1to5", "noise_1to5", "actionability_1to5", "coherence_1to5", "overall_1to5",
        "reviewer_notes",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for case, final_report in cases_with_reports:
            n_findings = sum(len(final_report.get(k, [])) for k in
                              ("security_issues", "bugs", "style_violations", "patches", "test_cases"))
            is_clean = case.get("is_clean", False)
            known_issue_desc = (
                "N/A — clean case, correct answer is an empty/near-empty report"
                if is_clean else case["known_issue"]["description"]
            )
            writer.writerow({
                "case_id": case["case_id"],
                "is_clean": is_clean,
                "pr_diff_excerpt": case["pr_diff"][:300].replace("\n", " \\n "),
                "known_issue_description": known_issue_desc,
                "final_report_summary": f"{n_findings} total findings across all categories",
                "coverage_1to5": "", "noise_1to5": "", "actionability_1to5": "",
                "coherence_1to5": "", "overall_1to5": "", "reviewer_notes": "",
            })
    print(f"[e2e/review] wrote human rubric sample ({len(cases_with_reports)} rows) to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=None)
    args = parser.parse_args()
    run(args.n)
