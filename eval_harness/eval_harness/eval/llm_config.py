"""LLM configuration for eval_harness — the judge and the zero-shot
ablation baseline both need real model calls, wired here.

All settings are environment-variable driven, mirroring eval_PR's
config.py so both projects follow the same operational pattern even
though the code is not shared between them:

  ANTHROPIC_API_KEY            required for Claude models
  DEEPSEEK_API_KEY             required for DeepSeek models
  OPENAI_API_KEY               required for OpenAI models
  LLM_BASE_URL                 DeepSeek API endpoint (default: https://api.deepseek.com/anthropic)
  EVAL_HARNESS_JUDGE_MODEL      model used for Layer B/C judging (default: a strong Claude model)
  EVAL_HARNESS_BASELINE_MODEL   model used for the zero-shot ablation baseline (default: a fast/cheap Claude model)
  EVAL_HARNESS_MAX_TOKENS       max output tokens per call (default: 3000)

The judge and baseline models are intentionally different from each other
(and from whatever model the agents under test run on) — using one model
to both produce and grade output biases the grade toward what that model
already believes. Both models can be any provider below (Claude, DeepSeek,
OpenAI) — the GUI's model pickers set the env vars above at run time.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_env() -> None:
    """Load API keys from a .env file — this harness lives nested under the
    main repo (eval_harness/eval_harness/eval/), so the keys usually sit in
    the repo root's .env, not this process's shell environment. Tries the
    harness's own .env first, then walks up to the repo root's, mirroring
    eval_PR's startup.py candidate order."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for candidate in (
        here.parent.parent / ".env",  # eval_harness/eval_harness/.env
        here.parent.parent.parent / ".env",  # eval_harness/.env
        here.parent.parent.parent.parent / ".env",  # repo root .env
    ):
        if candidate.exists():
            load_dotenv(candidate, override=False)


_load_env()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/anthropic")

MAX_TOKENS = int(os.environ.get("EVAL_HARNESS_MAX_TOKENS", "3000"))

DEFAULT_JUDGE_MODEL = "claude-opus-4-8"
DEFAULT_BASELINE_MODEL = "claude-haiku-4-5-20251001"

# Models offered in the GUI's judge/baseline pickers, grouped by provider.
AVAILABLE_MODELS = {
    "anthropic": ["claude-sonnet-5", "claude-opus-4-8", "claude-opus-4-7", "claude-haiku-4-5-20251001"],
    "deepseek": ["deepseek-v4-pro", "deepseek-v4-flash"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
}


def get_judge_model() -> str:
    """Read at call time (not import time) so the GUI can change
    EVAL_HARNESS_JUDGE_MODEL mid-process before triggering a run."""
    return os.environ.get("EVAL_HARNESS_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)


def get_baseline_model() -> str:
    return os.environ.get("EVAL_HARNESS_BASELINE_MODEL", DEFAULT_BASELINE_MODEL)


def get_provider_for_model(model: str) -> str:
    if model.startswith("deepseek"):
        return "deepseek"
    if model.startswith("gpt"):
        return "openai"
    return "anthropic"


def _api_key_for_provider(provider: str) -> str:
    return {
        "anthropic": ANTHROPIC_API_KEY,
        "deepseek": DEEPSEEK_API_KEY,
        "openai": OPENAI_API_KEY,
    }.get(provider, "")


def api_key_configured(model: str | None = None) -> bool:
    """With no model, True if ANY provider has a key configured. With a
    model, True only if that model's specific provider has a key."""
    if model is None:
        return bool(ANTHROPIC_API_KEY or DEEPSEEK_API_KEY or OPENAI_API_KEY)
    return bool(_api_key_for_provider(get_provider_for_model(model)))


def get_client(model: str = DEFAULT_JUDGE_MODEL):
    """Returns a provider-appropriate client for `model` if the SDK is
    installed and that provider's API key is configured, else None.
    Callers should treat None as "run in placeholder mode" rather than
    raising. DeepSeek is called through the Anthropic SDK against its
    Anthropic-compatible endpoint; OpenAI needs its own SDK/response shape,
    handled by `call_llm` below rather than here."""
    provider = get_provider_for_model(model)
    api_key = _api_key_for_provider(provider)
    if not api_key:
        return None
    try:
        if provider == "openai":
            import openai

            return openai.OpenAI(api_key=api_key)
        import anthropic

        if provider == "deepseek":
            return anthropic.Anthropic(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        return None


def call_llm(model: str, prompt: str, max_tokens: int | None = None) -> str:
    """Provider-aware single-turn call. Returns "" if no client/key is
    available for `model`'s provider — same placeholder behavior regardless
    of provider, so callers don't need per-provider branching."""
    client = get_client(model)
    if client is None:
        return ""
    max_tokens = max_tokens or MAX_TOKENS
    if get_provider_for_model(model) == "openai":
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
