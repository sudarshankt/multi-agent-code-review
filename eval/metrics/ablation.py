from __future__ import annotations

from typing import Sequence

from eval.metrics.classification import calculate_binary_metrics


def compute_majority_class_baseline(y_true: Sequence[int]) -> dict[str, float]:
    """Compute a deterministic zero-shot-style baseline using the majority label."""
    if not y_true:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    majority_label = 1 if sum(y_true) >= (len(y_true) / 2.0) else 0
    predictions = [majority_label] * len(y_true)
    return calculate_binary_metrics(list(y_true), predictions)


def compute_patch_baseline() -> dict[str, float]:
    """Use a no-op patch as the zero-shot proxy baseline."""
    return {"patch_pass_rate": 0.0, "po_c_reproduction_rate": 0.0}


def compute_style_baseline() -> dict[str, float]:
    """Use a no-op style detector as the zero-shot proxy baseline."""
    return {"agreement": 0.0, "false_positive_rate": 1.0}


def compute_rag_baseline() -> dict[str, float]:
    """Use an empty-context retrieval baseline for RAG evaluation."""
    return {"faithfulness": 0.0, "answer_relevance": 0.0, "context_precision": 0.0}
