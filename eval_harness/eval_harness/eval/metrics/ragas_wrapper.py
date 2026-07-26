"""Thin wrapper around the `ragas` library for Faithfulness and Answer
Relevance, per Section 4 of the instructions doc. Degrades gracefully
(raises a clear ImportError-derived message) if ragas isn't installed,
so the rest of the harness can still be imported/tested without it.
"""
from __future__ import annotations

from typing import Any


class RagasNotInstalled(RuntimeError):
    pass


def evaluate_rag_traces(
    questions: list[str],
    answers: list[str],
    contexts: list[list[str]],
    ground_truths: list[str] | None = None,
) -> dict:
    """Run RAGAS Faithfulness + Answer Relevance (+ Context Precision/Recall
    if ground_truths is given) over a batch of RAG traces.

    Each of questions/answers/contexts (and ground_truths, if given) must
    be the same length — one entry per retrieval trace.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as e:
        raise RagasNotInstalled(
            "ragas (and its `datasets` dependency) is required for RAG eval. "
            "Install with: pip install ragas datasets --break-system-packages"
        ) from e

    data: dict[str, Any] = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
    }
    metrics = [faithfulness, answer_relevancy]
    if ground_truths:
        data["ground_truth"] = ground_truths
        metrics += [context_precision, context_recall]

    dataset = Dataset.from_dict(data)
    result = evaluate(dataset, metrics=metrics)
    df = result.to_pandas()

    summary = {
        "faithfulness_mean": round(float(df["faithfulness"].mean()), 4),
        "answer_relevancy_mean": round(float(df["answer_relevancy"].mean()), 4),
        "n": len(df),
    }
    if ground_truths:
        summary["context_precision_mean"] = round(float(df["context_precision"].mean()), 4)
        summary["context_recall_mean"] = round(float(df["context_recall"].mean()), 4)

    summary["per_example"] = df.to_dict(orient="records")
    return summary
