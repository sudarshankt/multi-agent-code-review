"""Cross-layer comparison: joins Layer A's per-example predictions with
Layer B's per-case judge scores on shared case_id, to answer "did the
agent get this right alone, but the full pipeline still miss it?" (or the
reverse — the agent was wrong alone, but the pipeline caught it anyway,
e.g. via another agent or RAG context).

Only meaningful when both layers were run with --shared, against the
same eval.shared_cases registry — otherwise there's no guaranteed overlap
in case_ids to join on, and this script will report near-zero matches
(which is itself a useful signal that --shared wasn't used).

Usage:
    python -m eval.shared_cases --n-seccodeplt 20 --n-bugsinpy 20   # once
    python -m eval.runners.run_security_eval --shared
    python -m eval.runners.run_bug_eval --shared
    python -m eval.e2e.build_pr_cases --shared
    python -m eval.e2e.run_e2e_review
    python -m eval.report.cross_layer_comparison
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


def _layer_a_per_example(results_dir: Path) -> dict[str, dict]:
    """Merge per_example lists from every Layer A result file that has one
    (currently: security, bug_detection — see their runners' --shared
    mode) into one case_id -> {correct, y_true, y_pred} lookup.
    """
    merged = {}
    for path in results_dir.glob("*.json"):
        if path.name in ("final_report.json", "release_gate.json", "judge_calibration.json"):
            continue
        record = _load_json(path)
        if not record:
            continue
        for ex in record.get("extra", {}).get("per_example", []):
            merged[ex["case_id"]] = {
                "layer_a_correct": ex["correct"],
                "layer_a_y_true": ex["y_true"],
                "layer_a_y_pred": ex["y_pred"],
                "layer_a_benchmark": record.get("benchmark"),
            }
    return merged


def _layer_b_per_case(results_dir: Path) -> dict[str, dict]:
    e2e = _load_json(results_dir / "full_pipeline__llm-judge-e2e.json")
    if not e2e:
        return {}
    out = {}
    for s in e2e.get("extra", {}).get("per_case_scores", []):
        if s.get("parse_error") or s.get("overall", 0) == 0:
            continue  # judge not wired yet — nothing real to compare
        out[s["case_id"]] = {
            "layer_b_coverage": s.get("coverage"),
            "layer_b_overall": s.get("overall"),
            "layer_b_is_clean": s.get("is_clean", False),
        }
    return out


def compare(results_dir: Path | None = None) -> dict:
    cfg = load_config()
    results_dir = results_dir or REPO_ROOT / cfg["paths"]["results_dir"]

    layer_a = _layer_a_per_example(results_dir)
    layer_b = _layer_b_per_case(results_dir)

    shared_ids = set(layer_a) & set(layer_b)

    if not layer_a:
        print("[cross_layer] no Layer A per-example data found — run runners with --shared first.")
    if not layer_b:
        print("[cross_layer] no real Layer B judge scores found — run run_e2e_review.py with a wired judge first.")
    if layer_a and layer_b and not shared_ids:
        print(
            "[cross_layer] Layer A and Layer B results exist but share NO case_ids — "
            "were both run with --shared against the same eval.shared_cases registry?"
        )

    agent_right_pipeline_wrong = []
    agent_wrong_pipeline_right = []
    both_right, both_wrong = [], []

    # "Pipeline right" proxy: coverage >= 4 counts as caught the issue (see
    # llm_judge.py's coverage definition — this is a threshold choice, not
    # a given; adjust if your team defines "caught it" differently.
    PIPELINE_RIGHT_THRESHOLD = 4

    for case_id in sorted(shared_ids):
        a = layer_a[case_id]
        b = layer_b[case_id]
        agent_right = a["layer_a_correct"]
        pipeline_right = b["layer_b_coverage"] is not None and b["layer_b_coverage"] >= PIPELINE_RIGHT_THRESHOLD

        row = {"case_id": case_id, **a, **b}
        if agent_right and not pipeline_right:
            agent_right_pipeline_wrong.append(row)
        elif not agent_right and pipeline_right:
            agent_wrong_pipeline_right.append(row)
        elif agent_right and pipeline_right:
            both_right.append(row)
        else:
            both_wrong.append(row)

    summary = {
        "n_shared_cases": len(shared_ids),
        "both_right": len(both_right),
        "both_wrong": len(both_wrong),
        "agent_right_pipeline_wrong": len(agent_right_pipeline_wrong),
        "agent_wrong_pipeline_right": len(agent_wrong_pipeline_right),
        "pipeline_right_threshold_used": PIPELINE_RIGHT_THRESHOLD,
    }

    print(f"\n{'Category':<32} n")
    print("-" * 40)
    for label, count in [
        ("Both agent & pipeline right", summary["both_right"]),
        ("Both agent & pipeline wrong", summary["both_wrong"]),
        ("Agent right, pipeline wrong", summary["agent_right_pipeline_wrong"]),
        ("Agent wrong, pipeline right", summary["agent_wrong_pipeline_right"]),
    ]:
        print(f"{label:<32} {count}")
    print(f"\n(out of {len(shared_ids)} cases with results in both layers)\n")

    if agent_right_pipeline_wrong:
        print(
            "Cases where the agent alone was right but the full pipeline missed it "
            "(worth investigating — another agent or the supervisor may be suppressing "
            "a correct finding):"
        )
        for row in agent_right_pipeline_wrong:
            print(f"  {row['case_id']}")

    out_path = results_dir / "cross_layer_comparison.json"
    with open(out_path, "w") as f:
        json.dump({
            "summary": summary,
            "agent_right_pipeline_wrong": agent_right_pipeline_wrong,
            "agent_wrong_pipeline_right": agent_wrong_pipeline_right,
        }, f, indent=2)
    print(f"\n[cross_layer] wrote {out_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    compare()
