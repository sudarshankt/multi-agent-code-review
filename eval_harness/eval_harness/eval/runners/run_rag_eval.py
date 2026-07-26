"""RAG Pipeline evaluation runner.

Benchmarks (Section 2):
  - RAGAS Faithfulness >0.75, Answer Relevance >0.70 (from proposal)
  - Human-checked OWASP/CWE citation sample (added) — domain-grounds the
    generic RAGAS thresholds; see eval/human_eval/sample_for_review.py

Usage:
    python -m eval.runners.run_rag_eval
"""
from __future__ import annotations

import argparse
import json

from eval.agent_interface import rag_answer_with_context
from eval.common import REPO_ROOT, load_config, write_result
from eval.datasets.prepare_owasp_cwe import cwe_supports_claim
from eval.metrics.ragas_wrapper import RagasNotInstalled, evaluate_rag_traces


def _load_questions(n: int) -> list[str]:
    """OWASP/CWE-grounded question set for the RAG pipeline. Replace this
    with your team's actual retrieval eval set (e.g. sampled from real
    security findings the pipeline has produced)."""
    cfg = load_config()
    path = REPO_ROOT / cfg["paths"]["dataset_dir"] / "rag_eval_questions.jsonl"
    if not path.exists():
        print(
            f"[rag] {path} not found — using a tiny built-in placeholder "
            "set. Replace with real sampled questions before the final run."
        )
        return [
            "Why is string concatenation in SQL queries flagged as CWE-89?",
            "What OWASP category covers missing access control checks?",
        ][:n]
    questions = []
    with open(path) as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line)["question"])
    return questions[:n]


def run_ragas(n: int | None = None) -> dict:
    cfg = load_config()
    n = n or cfg["sample_sizes"]["ragas_n"]
    questions = _load_questions(n)

    answers, contexts = [], []
    for q in questions:
        answer, ctx = rag_answer_with_context(q)
        answers.append(answer)
        contexts.append(ctx if ctx else ["<no context retrieved>"])

    try:
        result = evaluate_rag_traces(questions, answers, contexts)
    except RagasNotInstalled as e:
        print(f"[rag/ragas] {e}")
        return {}

    metrics = {
        "faithfulness": result["faithfulness_mean"],
        "answer_relevancy": result["answer_relevancy_mean"],
        "n": result["n"],
    }
    cfg_t = cfg["thresholds"]
    metrics["meets_faithfulness_target"] = metrics["faithfulness"] >= cfg_t["ragas_faithfulness_target"]
    metrics["meets_relevance_target"] = metrics["answer_relevancy"] >= cfg_t["ragas_answer_relevance_target"]

    out = write_result(benchmark="RAGAS", agent="rag_pipeline", n=metrics["n"], metrics=metrics)
    print(f"[rag/ragas] wrote {out}  faithfulness={metrics['faithfulness']}  relevancy={metrics['answer_relevancy']}")
    return metrics


def run_citation_grounding_check(n: int | None = None) -> dict:
    """Cheap automated pre-filter for the human-checked citation sample
    (Section 2, row 2). Flags likely-ungrounded citations for the human
    reviewer to prioritize; does NOT replace the human review itself —
    see eval/human_eval/sample_for_review.py.
    """
    cfg = load_config()
    n = n or cfg["sample_sizes"]["human_citation_review_n"]
    questions = _load_questions(n)

    flagged = []
    for q in questions:
        answer, ctx = rag_answer_with_context(q)
        # NOTE: replace this placeholder extraction with real parsing of
        # whatever CWE ID format the RAG pipeline cites in its answers.
        cited_cwe = next((tok for tok in answer.split() if tok.startswith("CWE-")), None)
        if cited_cwe and not cwe_supports_claim(cited_cwe, answer):
            flagged.append({"question": q, "answer": answer, "cited_cwe": cited_cwe})

    metrics = {"n_checked": len(questions), "n_flagged_for_human_review": len(flagged)}
    out = write_result(
        benchmark="citation-grounding-prefilter",
        agent="rag_pipeline",
        n=len(questions),
        metrics=metrics,
        extra={"flagged": flagged},
    )
    print(f"[rag/citation-check] wrote {out}  flagged={len(flagged)}/{len(questions)}")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=["ragas", "citation", "all"], default="all")
    parser.add_argument("--n", type=int, default=None)
    args = parser.parse_args()

    if args.benchmark in ("ragas", "all"):
        run_ragas(args.n)
    if args.benchmark in ("citation", "all"):
        run_citation_grounding_check(args.n)
