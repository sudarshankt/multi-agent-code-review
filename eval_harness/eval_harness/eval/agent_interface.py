"""Plug points into the real multi-agent pipeline.

The eval harness is intentionally decoupled from the app (Section 1:
"standalone evaluation harness (separate from the app pipeline)"). Most
functions below are stubs with a clearly-marked TODO — replace the body
with a call into your actual LangGraph agents (e.g. import the compiled
graph and invoke the relevant node directly, or hit the FastAPI endpoint).

The one exception is `zero_shot_llm_call` — the ablation baseline doesn't
need your product's agent code at all, just a plain LLM call, so it's
wired to a real Anthropic API call (see eval/llm_config.py) rather than
left as a stub.

Until the remaining stubs are wired up, each returns a deterministic-but-
fake prediction so the rest of the harness (metrics, bootstrap CI,
aggregation, report generation) can be developed and tested end-to-end
without the app running.
"""
from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)


def _fake_binary_prediction(seed_text: str) -> int:
    """Deterministic pseudo-random 0/1 based on a hash — NOT a real model,
    just enough to exercise the metrics pipeline before the real agent is
    wired in."""
    h = int(hashlib.sha256(seed_text.encode()).hexdigest(), 16)
    return h % 2


def predict_vulnerability(code: str) -> int:
    """TODO: replace with a call to the Security Agent.
    Return 1 if the agent flags `code` as vulnerable, else 0.

    Example real implementation:
        from app.agents.security_agent import security_agent_node
        result = security_agent_node({"source_code": code})
        return 1 if result["security_issues"] else 0
    """
    return _fake_binary_prediction(code)


def predict_bug(code: str, repo_context: str | None = None) -> int:
    """TODO: replace with a call to the Bug Detection Agent.
    Return 1 if the agent flags `code` (with optional repo_context) as buggy.
    """
    return _fake_binary_prediction((repo_context or "") + code)


def generate_patch(vulnerable_code: str, description: str) -> str:
    """TODO: replace with a call to the Patch Generation Agent.
    Return the patched code (or a unified diff string, matching whatever
    the Patch Agent's PatchOutput schema produces).
    """
    return vulnerable_code  # no-op stub: "patch" that changes nothing


def style_flags(code: str) -> set[tuple]:
    """TODO: replace with a call to the Style Agent.
    Return a set of (line_number, rule_id) flags, matching Pylint's own
    flag format so pep8_agreement() can compare them directly.
    """
    return set()


def rag_answer_with_context(question: str) -> tuple[str, list[str]]:
    """TODO: replace with a call to the RAG pipeline.
    Return (answer_text, retrieved_context_chunks).
    """
    return ("", [])


def run_full_pipeline(pr_diff: str) -> dict:
    """TODO: replace with a call to the FULL LangGraph pipeline (supervisor
    + all agents), not an individual agent function. This is the plug
    point for eval/e2e/ — end-to-end PR review quality evaluation, as
    opposed to eval/runners/ which score individual agents in isolation.

    Must return the same structured "final report" object your app
    actually produces for a PR, e.g. matching your FinalReport Pydantic
    model:
        {
          "security_issues": [...],
          "bugs": [...],
          "style_violations": [...],
          "patches": [...],
          "test_cases": [...],
        }

    Example real implementation:
        from app.graph import compiled_graph
        result = compiled_graph.invoke({"source_code": pr_diff})
        return result["final_report"]
    """
    return {
        "security_issues": [],
        "bugs": [],
        "style_violations": [],
        "patches": [],
        "test_cases": [],
    }


def zero_shot_llm_call(prompt: str, model: str | None = None) -> str:
    """Real single-shot LLM call (no LangGraph, no RAG, no supervisor) —
    this is the ablation baseline from Section 4/Cross-cutting row 1.
    Uses BASELINE_MODEL from eval.llm_config by default (deliberately a
    different, cheaper/faster model than the judge, and different from
    whatever the agents under test run on). Cached via LLMCache so
    repeated runs don't re-spend API budget. Returns "" (same as the
    unwired placeholder) if no API key is configured or the call fails,
    so callers can't tell the difference between "not wired" and "call
    failed" from the return value alone — check eval.llm_config.api_key_configured()
    if that distinction matters to your use of this function.
    """
    from eval.common import LLMCache
    from eval.llm_config import BASELINE_MODEL, MAX_TOKENS, get_client

    resolved_model = model or BASELINE_MODEL
    client = get_client()
    if client is None:
        logger.info("No API key configured — returning empty placeholder zero-shot response.")
        return ""

    def _call() -> str:
        response = client.messages.create(
            model=resolved_model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    try:
        return LLMCache().get_or_call(prompt, resolved_model, _call)
    except Exception as e:
        logger.error("Zero-shot baseline API call failed: %s", e)
        return ""
