"""Configuration for eval_PR.

All settings are environment-variable driven so this tool can be deployed
without editing source code:

  ANTHROPIC_API_KEY        required for Claude models
  LLM_API_KEY              required for DeepSeek models (legacy)
  DEEPSEEK_API_KEY         required for DeepSeek models
  OPENAI_API_KEY           required for OpenAI models
  LLM_BASE_URL             DeepSeek API endpoint (default: https://api.deepseek.com/anthropic)
  EVAL_PR_JUDGE_MODEL       model used to audit the PR (default: claude-opus-4-8)
  EVAL_PR_BASELINE_MODEL    model used for the zero-shot baseline (default: deepseek-chat)
  EVAL_PR_MAX_TOKENS        max output tokens per call (default: 3000)

The judge and baseline models are intentionally different from each other
(and from whatever model your own multi-agent system runs on) — using the
same model to both produce and grade output biases the grade toward
whatever that model already believes.
"""
from __future__ import annotations

import os

JUDGE_MODEL = os.environ.get("EVAL_PR_JUDGE_MODEL", "claude-opus-4-8")
BASELINE_MODEL = os.environ.get("EVAL_PR_BASELINE_MODEL", "deepseek-v4-pro")
MAX_TOKENS = int(os.environ.get("EVAL_PR_MAX_TOKENS", "3000"))

# API Keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/anthropic")

# Available models per provider - tested and working with current API keys
# NOTE: Only include models that successfully parse JSON responses and return real verdicts
# Tested 2026-07-23: gpt-5.x series excluded (require max_completion_tokens, not max_tokens - unsupported by current call path)
AVAILABLE_MODELS = {
    "anthropic": [
        "claude-sonnet-5",              # Latest Sonnet - best for general use
        "claude-opus-4-8",              # Latest Opus - high-capability reasoning
        "claude-opus-4-7",              # Mid-tier Opus
    ],
    "deepseek": ["deepseek-v4-pro", "deepseek-v4-flash"],
    "openai": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini"],
}

# Recommended models for audit judge/baseline (exclude code-specific models)
# For audit tasks: use chat/reasoning models, not code-specific models
# Note: Gemini removed - free tier quota exhausted
# Note: Only includes models that successfully produce JSON with verdict fields
# Note: DeepSeek updated to v4 API (2026-07-24) - deepseek-chat no longer supported
AUDIT_MODELS = {
    "anthropic": [
        "claude-sonnet-5",              # Best for audit tasks
        "claude-opus-4-8",
        "claude-opus-4-7",
    ],
    "deepseek": ["deepseek-v4-pro", "deepseek-v4-flash"],
    "openai": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini"],
}



def api_key_configured(api_key: str | None = None) -> bool:
    """Check if any API key is configured, or a specific key if provided."""
    if api_key:
        return bool(api_key)
    return bool(ANTHROPIC_API_KEY or DEEPSEEK_API_KEY or OPENAI_API_KEY or GEMINI_API_KEY)


def get_provider_for_model(model: str) -> str:
    """Determine the provider for a given model name."""
    if model.startswith("deepseek"):
        return "deepseek"
    elif model.startswith("gpt-") or model.startswith("gpt4"):
        return "openai"
    elif model.startswith("gemini"):
        return "gemini"
    elif model.startswith("claude"):
        return "anthropic"
    else:
        return "anthropic"  # Default





def get_client_for_model(model: str, api_keys: dict | None = None):
    """Returns the appropriate client for the given model.
    
    Args:
        model: Model identifier (e.g., 'deepseek-chat', 'gpt-4', 'claude-opus')
        api_keys: Optional dict with keys: {'anthropic', 'deepseek', 'openai'}
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if api_keys is None:
        logger.debug("get_client_for_model: api_keys is None, using environment variables")
        api_keys = {
            "anthropic": ANTHROPIC_API_KEY,
            "deepseek": DEEPSEEK_API_KEY,
            "openai": OPENAI_API_KEY,
        }
    else:
        logger.debug("get_client_for_model: api_keys dict provided")
    
    provider = get_provider_for_model(model)
    api_key = api_keys.get(provider, "")
    
    logger.debug(f"get_client_for_model: model={model}, provider={provider}, key_available={bool(api_key)}")
    
    if not api_key:
        logger.debug(f"  -> No API key for {provider}, returning None")
        return None
    
    try:
        if provider == "deepseek":
            import anthropic
            logger.debug(f"  -> Creating Anthropic client for DeepSeek (base_url={DEEPSEEK_BASE_URL})")
            # DeepSeek API is compatible with Anthropic SDK
            return anthropic.Anthropic(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        elif provider == "anthropic":
            import anthropic
            logger.debug(f"  -> Creating Anthropic client for Anthropic")
            return anthropic.Anthropic(api_key=api_key)
        elif provider == "openai":
            import openai
            logger.debug(f"  -> Creating OpenAI client")
            return openai.OpenAI(api_key=api_key)
        else:
            logger.debug(f"  -> Unknown provider {provider}, returning None")
            return None
    except ImportError as e:
        logger.error(f"  -> Import error: {e}")
        return None
    except Exception as e:
        logger.error(f"  -> Error creating client: {e}")
        return None


def get_client():
    """Legacy function: returns a client for the judge model (kept for compatibility)."""
    return get_client_for_model(JUDGE_MODEL)


__all__ = [
    "JUDGE_MODEL",
    "BASELINE_MODEL",
    "MAX_TOKENS",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "AVAILABLE_MODELS",
    "AUDIT_MODELS",
    "api_key_configured",
    "get_provider_for_model",
    "get_client_for_model",
    "get_client",
]
