from __future__ import annotations

import math
import random
from collections import Counter
from typing import Sequence


def calculate_binary_metrics(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, float]:
    """Calculate precision, recall, and F1 for binary labels."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def bootstrap_confidence_interval(values: Sequence[float], n_bootstrap: int = 1000) -> list[float]:
    """Bootstrap a 95% confidence interval for a binary metric mean."""
    if not values:
        return [0.0, 0.0]

    rng = random.Random(42)
    estimates: list[float] = []
    n = len(values)

    for _ in range(n_bootstrap):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        estimates.append(sum(sample) / len(sample))

    estimates.sort()
    lower = estimates[int(math.floor(0.025 * n_bootstrap))]
    upper = estimates[int(math.ceil(0.975 * n_bootstrap)) - 1]
    return [lower, upper]
