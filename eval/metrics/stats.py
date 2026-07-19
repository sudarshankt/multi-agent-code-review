from __future__ import annotations

import math
import random
from collections.abc import Sequence

from eval.metrics.classification import calculate_binary_metrics


def bootstrap_binary_metric_ci(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    metric: str = "f1",
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> list[float]:
    """Estimate a 95% confidence interval by bootstrap-resampling examples."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    if not y_true:
        return [0.0, 0.0]

    rng = random.Random(seed)
    indices = list(range(len(y_true)))
    estimates: list[float] = []

    for _ in range(n_bootstrap):
        sample_idx = [indices[rng.randrange(len(indices))] for _ in indices]
        sample_true = [y_true[i] for i in sample_idx]
        sample_pred = [y_pred[i] for i in sample_idx]
        metrics = calculate_binary_metrics(sample_true, sample_pred)
        estimates.append(float(metrics.get(metric, 0.0)))

    estimates.sort()
    lower = estimates[int(math.floor(0.025 * n_bootstrap))]
    upper = estimates[int(math.ceil(0.975 * n_bootstrap)) - 1]
    return [lower, upper]
