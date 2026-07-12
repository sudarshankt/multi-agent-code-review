"""LangGraph state definition with Annotated reducers for parallel writes."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph import add_messages

from src.models.finding import Finding
from src.models.review import PRInfo, ReviewStatus


def add_findings(left: list[Finding], right: list[Finding]) -> list[Finding]:
    """Reducer: append findings from parallel agents."""
    return left + right


def add_agent_results(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """Reducer: merge agent result dicts."""
    merged = dict(left)
    merged.update(right)
    return merged


def add_files_bypassed(left: int, right: int) -> int:
    """Reducer: sum bypassed file counts from parallel agents."""
    return left + right


class PRReviewState(TypedDict):
    """Mutable state passed through the LangGraph pipeline."""

    # ---- Input ----
    pr_info: PRInfo
    files: dict[str, str]
    diffs: dict[str, str]
    review_id: str  # For SSE event publishing

    # ---- Running ----
    status: ReviewStatus

    # ---- Output (parallel writes via Annotated reducers) ----
    # List of all findings discovered by the 4 analysis agents.
    findings: Annotated[list[Finding], add_findings]
    # Per-agent results: {agent_name: AgentResult}
    agent_results: Annotated[dict[str, Any], add_agent_results]
    # Fix results from FixAgent (if applied).
    fix_results: list[Any]

    # ---- Metadata ----
    errors: list[str]
    files_bypassed: Annotated[int, add_files_bypassed]
