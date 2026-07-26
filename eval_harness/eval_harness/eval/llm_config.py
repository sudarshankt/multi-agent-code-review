"""LLM configuration for eval_harness — the judge and the zero-shot
ablation baseline both need real model calls, wired here.

All settings are environment-variable driven, mirroring eval_PR's
config.py so both projects follow the same operational pattern even
though the code is not shared between them:

  ANTHROPIC_API_KEY            required for real (non-placeholder) results
  EVAL_HARNESS_JUDGE_MODEL      model used for Layer B/C judging (default: a strong model)
  EVAL_HARNESS_BASELINE_MODEL   model used for the zero-shot ablation baseline (default: a fast/cheap model)
  EVAL_HARNESS_MAX_TOKENS       max output tokens per call (default: 3000)

The judge and baseline models are intentionally different from each other
(and from whatever model the agents under test run on) — using one model
to both produce and grade output biases the grade toward what that model
already believes.
"""
from __future__ import annotations

import os

JUDGE_MODEL = os.environ.get("EVAL_HARNESS_JUDGE_MODEL", "claude-opus-4-8")
BASELINE_MODEL = os.environ.get("EVAL_HARNESS_BASELINE_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS = int(os.environ.get("EVAL_HARNESS_MAX_TOKENS", "3000"))


def api_key_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_client():
    """Returns an anthropic.Anthropic() client if the SDK is installed and
    an API key is configured, else None. Callers should treat None as
    "run in placeholder mode" rather than raising."""
    if not api_key_configured():
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic()
