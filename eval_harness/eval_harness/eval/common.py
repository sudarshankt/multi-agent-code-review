"""Shared helpers used across every runner: config loading, disk cache for
LLM calls, a latency-tracking timer, and a small results-writer that
enforces the schema in Section 6 of the instructions doc.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent  # eval_harness/


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else REPO_ROOT / "eval" / "config.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


class Timer:
    """Minimal latency tracker — wrap any call (agent invocation, judge
    call, full pipeline run) to record wall-clock seconds. Addresses the
    "no latency/cost metrics" gap: nothing in the harness measured review
    time or per-call cost before this. Use as a context manager:

        with Timer() as t:
            result = run_full_pipeline(pr_diff)
        print(t.elapsed_seconds)

    For a whole batch, use `Timer.summarize()` on a list of elapsed times
    to get mean/p50/p95 — the numbers worth reporting for a "how long does
    a PR review take" story, not just the mean (which hides tail latency).
    """

    def __enter__(self) -> "Timer":
        self._start = time.monotonic()
        self.elapsed_seconds = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.elapsed_seconds = round(time.monotonic() - self._start, 4)

    @staticmethod
    def summarize(elapsed_seconds_list: list[float]) -> dict:
        if not elapsed_seconds_list:
            return {"n": 0, "mean_s": 0.0, "p50_s": 0.0, "p95_s": 0.0, "max_s": 0.0}
        s = sorted(elapsed_seconds_list)
        n = len(s)
        return {
            "n": n,
            "mean_s": round(sum(s) / n, 3),
            "p50_s": round(s[n // 2], 3),
            "p95_s": round(s[min(n - 1, int(n * 0.95))], 3),
            "max_s": round(s[-1], 3),
        }


class LLMCache:
    """Disk-backed cache keyed by a hash of the prompt (+ model + params).

    Per Section 5 of the instructions doc: "Cache every LLM call to disk,
    keyed by prompt hash — reruns during development should not re-spend
    API budget." Also records elapsed_seconds and a rough token-count
    proxy (character count / 4) for each non-cached call, so cost/latency
    can be aggregated later without needing a separate tracking system.
    """

    def __init__(self, cache_dir: str | Path | None = None):
        cfg = load_config()
        self.cache_dir = Path(cache_dir or REPO_ROOT / cfg["paths"]["cache_dir"])
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(prompt: str, model: str, **params: Any) -> str:
        blob = json.dumps({"prompt": prompt, "model": model, **params}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get_or_call(
        self,
        prompt: str,
        model: str,
        call_fn: Callable[[], str],
        **params: Any,
    ) -> str:
        """Return the cached response for (prompt, model, params) if present,
        otherwise call call_fn(), cache the result (with latency + a rough
        token-count proxy), and return it.
        """
        key = self._key(prompt, model, **params)
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            with open(cache_file, "r") as f:
                return json.load(f)["response"]

        with Timer() as t:
            response = call_fn()

        with open(cache_file, "w") as f:
            json.dump(
                {
                    "prompt": prompt,
                    "model": model,
                    "params": params,
                    "response": response,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": t.elapsed_seconds,
                    # rough proxy only (~4 chars/token for English text) —
                    # swap for the API response's real usage field if your
                    # client exposes one, that's always more accurate
                    "approx_prompt_tokens": len(prompt) // 4,
                    "approx_response_tokens": len(response) // 4,
                },
                f,
                indent=2,
            )
        return response


def write_result(
    benchmark: str,
    agent: str,
    n: int,
    metrics: dict,
    baseline_zero_shot: dict | None = None,
    extra: dict | None = None,
    results_dir: str | Path | None = None,
) -> Path:
    """Write one runner's result as JSON matching the Section 6 schema:

    {
      "benchmark": "PrimeVul",
      "agent": "security",
      "n": 500,
      "metrics": {...},
      "baseline_zero_shot": {...},
      "timestamp": "ISO8601"
    }
    """
    cfg = load_config()
    results_dir = Path(results_dir or REPO_ROOT / cfg["paths"]["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "benchmark": benchmark,
        "agent": agent,
        "n": n,
        "metrics": metrics,
        "baseline_zero_shot": baseline_zero_shot or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        record["extra"] = extra

    safe_name = f"{agent}__{benchmark}".lower().replace(" ", "_").replace("/", "-")
    out_path = results_dir / f"{safe_name}.json"
    with open(out_path, "w") as f:
        json.dump(record, f, indent=2)
    return out_path
