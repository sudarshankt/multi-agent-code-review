"""Zero-shot baseline: what a single plain LLM call produces for a PR,
with no multi-agent pipeline. Used only for comparison against the
system's Fixed Code — never gates the verdict, only shows the delta a
multi-agent architecture adds over a single prompt.
"""
from __future__ import annotations

import logging

from eval_pr.config import BASELINE_MODEL, MAX_TOKENS, get_client_for_model, get_provider_for_model

logger = logging.getLogger(__name__)

ZERO_SHOT_PROMPT_TEMPLATE = """You are a code reviewer. Review this pull request in a single pass — no
multi-step process, just your direct assessment. Identify any security, bug, style, or
performance issues you see, and suggest a patch if you find something worth fixing.

=== PR ===
{pr}

Respond with your findings and suggested patch in plain text.
"""


def _call_zero_shot_llm(prompt: str, model: str = BASELINE_MODEL, api_keys: dict | None = None, max_tokens: int = MAX_TOKENS) -> str:
    """Calls the baseline model if API key is configured; otherwise
    returns an empty string so the tool still runs end-to-end in demo mode.
    
    Args:
        prompt: The prompt to send to the model
        model: Model identifier (default: BASELINE_MODEL)
        api_keys: Optional dict with API keys for each provider
        max_tokens: Maximum tokens in response (default: MAX_TOKENS)
    """
    logger.debug(f"_call_zero_shot_llm: model={model}, api_keys={'dict' if api_keys else 'None'}")
    if api_keys:
        logger.debug(f"  api_keys contents: {{{', '.join(f'{k}: {'SET' if v else 'EMPTY'}' for k, v in api_keys.items())}}}")
    
    client = get_client_for_model(model, api_keys)
    logger.debug(f"  get_client_for_model returned: {type(client).__name__ if client else 'None'}")
    
    if client is None:
        logger.info(f"No API key configured for baseline model '{model}' — returning empty placeholder baseline.")
        return ""
    
    provider = get_provider_for_model(model)
    
    try:
        if provider == "openai":
            # OpenAI uses different API
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        else:
            # Anthropic and DeepSeek use same API
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            # Handle thinking blocks (extended thinking) - extract text content
            text_content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text_content += block.text
            return text_content if text_content else ""
    except Exception as e:
        logger.error("Baseline API call failed: %s", e)
        return ""


def generate_zero_shot_review(pr: str, baseline_model: str = BASELINE_MODEL, api_keys: dict | None = None, max_tokens: int = MAX_TOKENS) -> str:
    """Returns the baseline's plain-text review + suggested patch for this
    PR — fed into judge.score_rubric_only() for a like-for-like comparison
    against the multi-agent system's Fixed Code.
    
    Args:
        pr: The PR text
        baseline_model: Model to use for baseline (default: BASELINE_MODEL)
        api_keys: Optional dict with API keys for each provider
        max_tokens: Maximum tokens in response (default: MAX_TOKENS)
    """
    prompt = ZERO_SHOT_PROMPT_TEMPLATE.format(pr=pr)
    return _call_zero_shot_llm(prompt, model=baseline_model, api_keys=api_keys, max_tokens=max_tokens)
