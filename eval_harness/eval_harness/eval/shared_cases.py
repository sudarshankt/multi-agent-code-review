"""Shared case registry: a fixed, seeded subset of SecCodePLT/BugsInPy
examples that Layer A, Layer B, and Layer C all draw from — so a per-case
comparison across layers is possible ("did the Security Agent get this
right alone, but the full pipeline still missed it?").

Without this, each layer sampled independently: Layer A's per-agent
runners took the first N rows of each dataset, and Layer B/C's case
builders did their own independent sampling — same pools, but no
guarantee of the same individual examples. This module is the fix: build
the registry ONCE, and every layer that wants comparability loads from it
by explicit ID instead of by count.

Registry format (eval/data/shared_case_registry.json):
{
  "seccodeplt_indices": [12, 45, 88, ...],
  "bugsinpy_case_ids": ["httpie/1", "pandas/3", ...],
  "seed": 42,
  "n_seccodeplt": 20,
  "n_bugsinpy": 20
}

Usage:
    python -m eval.shared_cases --n-seccodeplt 20 --n-bugsinpy 20
"""
from __future__ import annotations

import argparse
import json
import random

from eval.common import REPO_ROOT, load_config

REGISTRY_REL_PATH = "shared_case_registry.json"


def build_registry(n_seccodeplt: int = 20, n_bugsinpy: int = 20, seed: int = 42) -> dict:
    from eval.datasets.download_bugsinpy import load_sample as load_bugsinpy
    from eval.datasets.download_seccodeplt import load_samples as load_seccodeplt

    cfg = load_config()
    rng = random.Random(seed)

    all_seccodeplt = load_seccodeplt(sample_n=999_999)  # force the true full pool, not the config default
    all_bugsinpy = load_bugsinpy(sample_n=999_999)

    seccodeplt_pool = [s["index"] for s in all_seccodeplt]
    bugsinpy_pool = [f"{b['project']}/{b['bug_id']}" for b in all_bugsinpy]

    seccodeplt_indices = sorted(rng.sample(seccodeplt_pool, min(n_seccodeplt, len(seccodeplt_pool))))
    bugsinpy_case_ids = sorted(rng.sample(bugsinpy_pool, min(n_bugsinpy, len(bugsinpy_pool))))

    registry = {
        "seccodeplt_indices": seccodeplt_indices,
        "bugsinpy_case_ids": bugsinpy_case_ids,
        "seed": seed,
        "n_seccodeplt": len(seccodeplt_indices),
        "n_bugsinpy": len(bugsinpy_case_ids),
    }

    out_path = REPO_ROOT / cfg["paths"]["dataset_dir"] / REGISTRY_REL_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(registry, f, indent=2)

    print(
        f"[shared_cases] wrote registry: {len(seccodeplt_indices)} SecCodePLT + "
        f"{len(bugsinpy_case_ids)} BugsInPy cases to {out_path}"
    )
    return registry


def load_registry() -> dict:
    cfg = load_config()
    path = REPO_ROOT / cfg["paths"]["dataset_dir"] / REGISTRY_REL_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m eval.shared_cases` first to build it — "
            "do this ONCE and commit the resulting registry file so every layer and every "
            "team member scores the same examples. Rebuilding with a different seed or n "
            "invalidates cross-layer comparisons made against the old registry."
        )
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-seccodeplt", type=int, default=20)
    parser.add_argument("--n-bugsinpy", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    build_registry(args.n_seccodeplt, args.n_bugsinpy, args.seed)
