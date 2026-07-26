"""Pull a random sample of generated patches (or flagged citations) into a
CSV for manual scoring, per Section 2's human-reviewed rows for the Patch
Agent and RAG Pipeline.

Usage:
    python -m eval.human_eval.sample_for_review --kind patches --n 40
    python -m eval.human_eval.sample_for_review --kind citations --n 40
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from eval.common import REPO_ROOT, load_config

TEMPLATE_HEADER_PATCHES = [
    "id", "benchmark", "vulnerable_code", "generated_patch", "cve_or_bug_id",
    "reviewer_verdict_pass_fail", "reviewer_rationale",
]
TEMPLATE_HEADER_CITATIONS = [
    "id", "question", "answer", "cited_cwe", "reviewer_verdict_supported_unsupported",
    "reviewer_rationale",
]


def sample_patches(n: int, seed: int = 42) -> Path:
    cfg = load_config()
    results_dir = REPO_ROOT / cfg["paths"]["results_dir"]
    candidates = []
    for f in results_dir.glob("patch_generation__*.json"):
        with open(f) as fh:
            record = json.load(fh)
        for i, item in enumerate(record.get("extra", {}).get("patches", [])):
            candidates.append({"id": f"{f.stem}-{i}", "benchmark": record["benchmark"], **item})

    if not candidates:
        print(
            "[human_eval] no patch records with an `extra.patches` list found in "
            f"{results_dir}. Runners currently don't attach individual patches to "
            "their result JSON — add an `extra={'patches': [...]}' to the "
            "write_result() call in run_patch_eval.py if you want this sampler "
            "to have real data to pull from. Writing an empty template instead."
        )

    random.Random(seed).shuffle(candidates)
    sample = candidates[:n]

    out_path = REPO_ROOT / "eval" / "human_eval" / "patch_review_sample.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TEMPLATE_HEADER_PATCHES)
        writer.writeheader()
        for row in sample:
            writer.writerow({k: row.get(k, "") for k in TEMPLATE_HEADER_PATCHES})
    print(f"[human_eval] wrote {len(sample)} rows to {out_path}")
    return out_path


def sample_citations(n: int, seed: int = 42) -> Path:
    cfg = load_config()
    results_dir = REPO_ROOT / cfg["paths"]["results_dir"]
    candidates = []
    for f in results_dir.glob("rag_pipeline__citation-grounding-prefilter.json"):
        with open(f) as fh:
            record = json.load(fh)
        for i, item in enumerate(record.get("extra", {}).get("flagged", [])):
            candidates.append({"id": f"{f.stem}-{i}", **item})

    random.Random(seed).shuffle(candidates)
    sample = candidates[:n]

    out_path = REPO_ROOT / "eval" / "human_eval" / "citation_review_sample.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TEMPLATE_HEADER_CITATIONS)
        writer.writeheader()
        for row in sample:
            writer.writerow({k: row.get(k, "") for k in TEMPLATE_HEADER_CITATIONS})
    print(f"[human_eval] wrote {len(sample)} rows to {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["patches", "citations"], required=True)
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.kind == "patches":
        sample_patches(args.n, args.seed)
    else:
        sample_citations(args.n, args.seed)
