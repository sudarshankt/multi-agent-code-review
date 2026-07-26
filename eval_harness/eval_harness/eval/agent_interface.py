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

import asyncio
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _ensure_repo_root_on_path() -> None:
    """Allow eval_harness to import project `src.*` regardless of cwd.

    When users launch from `eval_harness/eval_harness`, Python won't find
    the project root by default. We locate it relative to this file and
    prepend it to sys.path.
    """
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def _is_lenient_mode() -> bool:
    """Optional compatibility mode.

    Default is strict integration (raise on missing app deps). Set
    EVAL_HARNESS_LENIENT=1 to return safe empty outputs instead.
    """
    return os.getenv("EVAL_HARNESS_LENIENT", "0").lower() in {"1", "true", "yes"}


def _handle_integration_error(func_name: str, exc: Exception, default: Any) -> Any:
    logger.warning("%s_failed", func_name, exc_info=exc)
    if _is_lenient_mode():
        return default
    raise RuntimeError(
        f"{func_name} requires full app dependencies. Install root project deps first "
        f"(from repo root: pip install -e .) or run with EVAL_HARNESS_LENIENT=1. "
        f"Original error: {exc}"
    ) from exc


def _run_coro_sync(coro: Any) -> Any:
    """Run an async coroutine from sync contexts (CLI + Streamlit safe)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: asyncio.run(coro))
        return future.result()


def _files_payload_from_code(code: str, file_path: str = "eval_input.py") -> dict[str, str]:
    return {file_path: code or ""}


def _extract_files_from_unified_diff(pr_diff: str) -> tuple[dict[str, str], dict[str, str]]:
    """Best-effort extraction of per-file text from unified diffs.

    We keep added and context lines as synthetic file content so agents can run
    without a full repository checkout.
    """
    files: dict[str, list[str]] = {}
    diffs: dict[str, list[str]] = {}
    current_file: str | None = None

    for raw_line in pr_diff.splitlines():
        line = raw_line.rstrip("\n")

        if line.startswith("+++ b/"):
            current_file = line[6:]
            files.setdefault(current_file, [])
            diffs.setdefault(current_file, [])
            continue

        if current_file is None:
            continue

        diffs[current_file].append(line)

        if line.startswith("@@") or line.startswith("diff --git") or line.startswith("index ") or line.startswith("--- a/"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            files[current_file].append(line[1:])
        elif line.startswith(" "):
            files[current_file].append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            # Removed lines are not part of the resulting file state.
            continue
        else:
            # PR-shaped cases from the harness often provide `---/+++` headers
            # followed by raw file content (not +/- hunk lines).
            files[current_file].append(line)

    normalized_files = {
        fp: "\n".join(lines).strip() for fp, lines in files.items() if "\n".join(lines).strip()
    }
    normalized_diffs = {fp: "\n".join(lines) for fp, lines in diffs.items() if lines}
    return normalized_files, normalized_diffs


def _category_key(category_value: str) -> str:
    return {
        "security": "security_issues",
        "bug_detection": "bugs",
        "style": "style_violations",
        "performance": "performance_issues",
    }.get(category_value, "bugs")


def _finding_to_dict(finding: Any) -> dict[str, Any]:
    category = getattr(finding, "category", None)
    severity = getattr(finding, "severity", None)
    location = getattr(finding, "location", None)

    return {
        "id": getattr(finding, "id", ""),
        "category": getattr(category, "value", str(category or "")),
        "severity": getattr(severity, "value", str(severity or "")),
        "title": getattr(finding, "title", ""),
        "description": getattr(finding, "description", ""),
        "file_path": getattr(location, "file_path", ""),
        "start_line": getattr(location, "start_line", None),
        "end_line": getattr(location, "end_line", None),
        "suggestion": getattr(finding, "suggestion", None),
        "cwe_id": getattr(finding, "cwe_id", None),
        "agent_name": getattr(finding, "agent_name", None),
    }


def predict_vulnerability(code: str) -> int:
    """Run the real SecurityAgent when available.

    Returns 1 if findings are produced, else 0. Falls back to deterministic
    pseudo predictions when app dependencies are unavailable.
    """
    try:
        _ensure_repo_root_on_path()
        from src.agents.security.agent import SecurityAgent

        files = _files_payload_from_code(code)
        findings = _run_coro_sync(SecurityAgent().run(files, {"triage_enabled": True}))
        return 1 if findings else 0
    except Exception as exc:
        return _handle_integration_error("predict_vulnerability", exc, 0)


def predict_bug(code: str, repo_context: str | None = None) -> int:
    """Run the real BugDetectionAgent when available.

    Returns 1 if findings are produced, else 0. Falls back to deterministic
    pseudo predictions when app dependencies are unavailable.
    """
    try:
        _ensure_repo_root_on_path()
        from src.agents.bug_detection.agent import BugDetectionAgent

        files = _files_payload_from_code(code)
        context = {"triage_enabled": True, "repo_context": repo_context or ""}
        findings = _run_coro_sync(BugDetectionAgent().run(files, context))
        return 1 if findings else 0
    except Exception as exc:
        return _handle_integration_error("predict_bug", exc, 0)


def generate_patch(vulnerable_code: str, description: str) -> str:
    """Run FixAgent._fix_file with a synthetic finding derived from description.

    Returns patched code on success, otherwise returns the original input.
    """
    try:
        _ensure_repo_root_on_path()
        from src.agents.fix.agent import FixAgent
        from src.models.finding import Category, Confidence, Finding, Location, Severity

        category = Category.SECURITY if re.search(r"\b(cwe|cve|vuln|injection|xss|sql)\b", description, re.IGNORECASE) else Category.BUG
        seed_finding = Finding(
            category=category,
            severity=Severity.HIGH,
            confidence=Confidence.MEDIUM,
            title=(description or "Issue identified")[:200],
            description=description or "Issue identified",
            location=Location(file_path="eval_input.py", start_line=1, end_line=1),
        )

        async def _generate() -> str:
            agent = FixAgent()
            result, fixed_code = await agent._fix_file(
                vulnerable_code,
                "eval_input.py",
                [seed_finding],
                category.value,
            )
            if result.success and fixed_code:
                return fixed_code
            return vulnerable_code

        return _run_coro_sync(_generate())
    except Exception as exc:
        return _handle_integration_error("generate_patch", exc, vulnerable_code)


def style_flags(code: str) -> set[tuple]:
    """Run the real StyleAgent and normalize findings to (line, rule_id).

    Rule IDs are parsed from titles like ``E302: ...`` and default to
    ``AGENT`` when no linter-like code is present.
    """
    try:
        _ensure_repo_root_on_path()
        from src.agents.style.agent import StyleAgent

        files = _files_payload_from_code(code)
        findings = _run_coro_sync(StyleAgent().run(files, {"triage_enabled": True}))
        flags: set[tuple] = set()
        for finding in findings:
            line = finding.location.start_line or 1
            title = finding.title or ""
            rule_match = re.match(r"^([A-Z]\d{3,4})\s*:", title)
            rule_id = rule_match.group(1) if rule_match else "AGENT"
            flags.add((line, rule_id))
        return flags
    except Exception as exc:
        return _handle_integration_error("style_flags", exc, set())


def rag_answer_with_context(question: str) -> tuple[str, list[str]]:
    """Retrieve OWASP/CWE context and synthesize an answer with the app LLM.

    Returns (answer, chunks). If generation fails, returns empty answer with
    empty chunks.
    """
    try:
        _ensure_repo_root_on_path()
        from src.agents.security.retriever import SecurityRetriever
        from src.services.llm_service import get_llm_service

        retriever = SecurityRetriever(top_k=5)
        context_block = retriever.retrieve(question)
        chunks = [ln.strip().lstrip("- ").strip() for ln in context_block.splitlines() if ln.strip()]

        if not chunks:
            return ("", [])

        prompt = (
            "Answer the security question using only the provided context. "
            "If the context is insufficient, say so briefly.\n\n"
            f"Question: {question}\n\n"
            "Context:\n"
            f"{context_block}\n"
        )

        answer = _run_coro_sync(get_llm_service().complete(prompt))
        return (answer or "", chunks)
    except Exception as exc:
        return _handle_integration_error("rag_answer_with_context", exc, ("", []))


def run_full_pipeline(pr_diff: str) -> dict:
    """Run the real orchestrator graph on best-effort file extraction.

    Unified diff input is converted into synthetic per-file contents so the
    production graph can run without a repository checkout. Returns a stable
    final-report shape expected by eval/e2e.
    """
    files, diffs = _extract_files_from_unified_diff(pr_diff)
    if not files:
        files = _files_payload_from_code(pr_diff, file_path="pr_diff.txt")

    try:
        _ensure_repo_root_on_path()
        from src.agents.orchestrator.graph import get_graph
        from src.models.review import PRInfo, ReviewStatus

        input_state = {
            "pr_info": PRInfo(owner="eval", repo="eval_harness", pr_number=0, title="eval_harness_case"),
            "files": files,
            "diffs": diffs,
            "review_id": "eval-harness",
            "status": ReviewStatus.ANALYZING,
            "findings": [],
            "agent_results": {},
            "fix_results": [],
            "proposed_fixes": [],
            "errors": [],
            "files_bypassed": 0,
        }

        result = _run_coro_sync(get_graph().ainvoke(input_state))
    except Exception as exc:
        return _handle_integration_error(
            "run_full_pipeline",
            exc,
            {
                "security_issues": [],
                "bugs": [],
                "style_violations": [],
                "performance_issues": [],
                "patches": [],
                "test_cases": [],
                "errors": [str(exc)],
            },
        )

    findings = result.get("findings", [])
    grouped: dict[str, list[dict[str, Any]]] = {
        "security_issues": [],
        "bugs": [],
        "style_violations": [],
        "performance_issues": [],
    }
    for finding in findings:
        category = getattr(finding, "category", None)
        category_value = getattr(category, "value", str(category or "bug_detection"))
        grouped[_category_key(category_value)].append(_finding_to_dict(finding))

    proposals = result.get("proposed_fixes", [])
    patches = [
        {
            "id": p.id,
            "category": p.category,
            "file_path": p.file_path,
            "diff": p.diff,
            "explanation": p.explanation,
            "status": p.status.value,
        }
        for p in proposals
    ]

    return {
        **grouped,
        "patches": patches,
        "test_cases": [],
        "files_bypassed": result.get("files_bypassed", 0),
        "errors": result.get("errors", []),
    }


def zero_shot_llm_call(prompt: str, model: str | None = None) -> str:
    """Real single-shot LLM call (no LangGraph, no RAG, no supervisor) —
    this is the ablation baseline from Section 4/Cross-cutting row 1.
    Uses eval.llm_config.get_baseline_model() by default (deliberately a
    different, cheaper/faster model than the judge, and different from
    whatever the agents under test run on) — any provider (Claude,
    DeepSeek, OpenAI). Cached via LLMCache so repeated runs don't re-spend
    API budget. Returns "" (same as the unwired placeholder) if no API key
    is configured for that model's provider, or the call fails, so callers
    can't tell the difference between "not wired" and "call failed" from
    the return value alone — check eval.llm_config.api_key_configured()
    if that distinction matters to your use of this function.
    """
    from eval.common import LLMCache
    from eval.llm_config import api_key_configured, call_llm, get_baseline_model

    resolved_model = model or get_baseline_model()
    if not api_key_configured(resolved_model):
        logger.info("No API key configured for baseline model %s — returning empty placeholder zero-shot response.", resolved_model)
        return ""

    try:
        return LLMCache().get_or_call(prompt, resolved_model, lambda: call_llm(resolved_model, prompt))
    except Exception as e:
        logger.error("Zero-shot baseline API call failed: %s", e)
        return ""
