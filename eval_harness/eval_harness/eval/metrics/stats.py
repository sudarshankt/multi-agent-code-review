"""Bootstrap confidence intervals.

Per Section 4: "LLM outputs are non-deterministic, so a single-run point
estimate is not enough. Report as metric ± CI." Default n_resamples=1000
per Section 4, overridable via config.yaml's bootstrap block.
"""
from __future__ import annotations

import random
from typing import Callable, Sequence


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float] = lambda v: sum(v) / len(v),
    n_resamples: int = 1000,
    confidence_level: float = 0.95,
    seed: int | None = 42,
) -> dict:
    """Percentile bootstrap CI for an arbitrary statistic (default: mean).

    Use this on a list of per-example scores (e.g., 1/0 correctness, or
    per-example F1 if you're bootstrapping over repeated LLM runs) — not
    directly on a single aggregate number.
    """
    if not values:
        return {"point_estimate": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}

    rng = random.Random(seed)
    n = len(values)
    point_estimate = statistic(values)

    resample_stats = []
    for _ in range(n_resamples):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        resample_stats.append(statistic(resample))

    resample_stats.sort()
    alpha = 1 - confidence_level
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    hi_idx = min(hi_idx, n_resamples - 1)

    return {
        "point_estimate": round(point_estimate, 4),
        "ci_low": round(resample_stats[lo_idx], 4),
        "ci_high": round(resample_stats[hi_idx], 4),
        "n": n,
        "n_resamples": n_resamples,
        "confidence_level": confidence_level,
    }


def bootstrap_ci_from_config(values: Sequence[float], statistic=None) -> dict:
    """Convenience wrapper that reads n_resamples/confidence_level/seed
    from eval/config.yaml's `bootstrap` block."""
    from eval.common import load_config

    cfg = load_config()["bootstrap"]
    kwargs = dict(
        n_resamples=cfg["n_resamples"],
        confidence_level=cfg["confidence_level"],
        seed=cfg["random_seed"],
    )
    if statistic is not None:
        kwargs["statistic"] = statistic
    return bootstrap_ci(values, **kwargs)
