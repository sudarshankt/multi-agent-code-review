from __future__ import annotations

from collections.abc import Sequence

from eval.metrics.classification import calculate_binary_metrics


def compute_majority_class_baseline(y_true: Sequence[int]) -> dict[str, float]:
    """Compute a deterministic zero-shot-style baseline using the majority label."""
    if not y_true:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    majority_label = 1 if sum(y_true) >= (len(y_true) / 2.0) else 0
    predictions = [majority_label] * len(y_true)
    return calculate_binary_metrics(list(y_true), predictions)


def compute_patch_baseline() -> dict[str, float]:
    """Fallback patch baseline used when no benchmark outcomes are available."""
    return {"patch_pass_rate": 0.0, "po_c_reproduction_rate": 0.0}


def compute_style_baseline() -> dict[str, float]:
    """Fallback style baseline used when no benchmark features are available."""
    return {"agreement": 0.0, "false_positive_rate": 1.0}


def compute_rag_baseline() -> dict[str, float]:
    """Fallback RAG baseline used when no benchmark labels are available."""
    return {"faithfulness": 0.0, "answer_relevance": 0.0, "context_precision": 0.0}


def compute_patch_baseline_from_outcomes(outcomes: Sequence[bool]) -> dict[str, float]:
    """Compute a deterministic baseline patch pass rate from benchmark outcomes."""
    if not outcomes:
        return compute_patch_baseline()

    positives = sum(1 for item in outcomes if item)
    negatives = len(outcomes) - positives
    majority_positive = positives >= negatives
    predictions = [majority_positive] * len(outcomes)
    tp = sum(1 for pred, true in zip(predictions, outcomes, strict=True) if pred and true)
    return {
        "patch_pass_rate": tp / len(outcomes),
        "po_c_reproduction_rate": 0.0,
    }


def compute_style_baseline_from_labels(gold_labels: Sequence[bool], baseline_labels: Sequence[bool]) -> dict[str, float]:
    """Compute agreement and false-positive rate from style baseline predictions."""
    if not gold_labels or len(gold_labels) != len(baseline_labels):
        return compute_style_baseline()

    matches = sum(1 for g, p in zip(gold_labels, baseline_labels, strict=True) if g == p)
    false_positives = sum(1 for g, p in zip(gold_labels, baseline_labels, strict=True) if (not g) and p)
    negatives = sum(1 for g in gold_labels if not g)
    return {
        "agreement": matches / len(gold_labels),
        "false_positive_rate": (false_positives / negatives) if negatives else 0.0,
    }


def compute_rag_baseline_from_support_labels(support_labels: Sequence[bool]) -> dict[str, float]:
    """Compute a simple empty-context baseline from citation support labels."""
    if not support_labels:
        return compute_rag_baseline()

    # Empty-context proxy predicts unsupported for every claim.
    predicted_supported = [False] * len(support_labels)
    matches = sum(
        1
        for true_supported, pred_supported in zip(support_labels, predicted_supported, strict=True)
        if true_supported == pred_supported
    )
    baseline_score = matches / len(support_labels)
    return {
        "faithfulness": baseline_score,
        "answer_relevance": baseline_score,
        "context_precision": 0.0,
    }
