"""Deduplication logic for findings across agents.

When multiple agents report similar findings, deduplicate by keeping the most
specific/confident version and assigning it to the most appropriate category.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from src.core.logging import get_logger
from src.models.finding import Finding, Severity

logger = get_logger(__name__)

SEVERITY_RANK = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 4,
    Severity.MEDIUM: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}

CATEGORY_PRIORITY = {
    "security": 1,      # Highest priority for security findings
    "bug_detection": 2,
    "performance": 3,
    "style": 4,         # Lowest priority for style findings
}


def _similarity(a: str, b: str) -> float:
    """Calculate string similarity (0-1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _are_similar(finding1: Finding, finding2: Finding, threshold: float = 0.7) -> bool:
    """Check if two findings are similar (likely duplicates)."""
    # Same file and line range?
    if (
        finding1.location.file_path == finding2.location.file_path
        and finding1.location.start_line == finding2.location.start_line
        and finding1.location.end_line == finding2.location.end_line
    ):
        # Similar titles?
        title_sim = _similarity(finding1.title, finding2.title)
        if title_sim >= threshold:
            return True

    # Very similar titles even if different line numbers?
    title_sim = _similarity(finding1.title, finding2.title)
    if title_sim >= 0.85:
        return True

    return False


def deduplicate_findings(
    findings: list[Finding], agent_results: dict[str, Any]
) -> tuple[list[Finding], dict[str, Any]]:
    """
    Deduplicate findings across agents.

    For each group of similar findings, keep the highest-severity one and
    assign it to the most appropriate agent category.

    Returns:
        (deduplicated_findings, updated_agent_results)
    """
    if not findings:
        return findings, agent_results

    deduplicated = []
    used_indices = set()

    for i, finding in enumerate(findings):
        if i in used_indices:
            continue

        # Find all similar findings to this one
        similar_group = [finding]
        similar_indices = [i]

        for j in range(i + 1, len(findings)):
            if j not in used_indices and _are_similar(finding, findings[j]):
                similar_group.append(findings[j])
                similar_indices.append(j)

        # Pick the best one (highest severity, then confidence)
        best = max(
            similar_group,
            key=lambda f: (
                SEVERITY_RANK.get(f.severity, 0),
                1 if f.confidence == "high" else (0.5 if f.confidence == "medium" else 0),
            ),
        )

        # Reassign to most appropriate category based on content
        best_agent = _find_best_agent(best, agent_results)

        deduplicated.append(best)

        # Mark all as used
        for idx in similar_indices:
            used_indices.add(idx)

        # Log deduplication
        if len(similar_group) > 1:
            logger.info(
                "finding_deduplicated",
                title=best.title,
                duplicates_removed=len(similar_group) - 1,
                assigned_agent=best_agent,
            )

    # Update agent_results to reflect deduplication
    updated_results = _update_agent_results(deduplicated, agent_results)

    return deduplicated, updated_results


def _find_best_agent(finding: Finding, agent_results: dict[str, Any]) -> str:
    """Determine which agent should own this finding based on its content."""
    from src.core.constants import (
        AGENT_BUG,
        AGENT_PERFORMANCE,
        AGENT_SECURITY,
        AGENT_STYLE,
    )

    title_lower = finding.title.lower()
    desc_lower = finding.description.lower()
    content = f"{title_lower} {desc_lower}"

    # Security keywords
    security_keywords = [
        "injection", "xss", "csrf", "sql", "command", "path traversal",
        "deserialization", "hardcoded", "secret", "credential", "crypto",
        "encryption", "auth", "authorization", "ssrf", "vulnerability",
        "cwe-", "owasp",
    ]

    # Performance keywords
    perf_keywords = [
        "o(n^2)", "n+1", "inefficient", "slow", "memory leak", "leak",
        "hotspot", "bottleneck", "repeated", "loop", "unbounded",
    ]

    # Style keywords
    style_keywords = [
        "naming", "docstring", "documentation", "clarity", "readability",
        "unused", "dead code", "complex", "maintainability", "naming convention",
    ]

    # Count keyword matches
    security_score = sum(1 for kw in security_keywords if kw in content)
    perf_score = sum(1 for kw in perf_keywords if kw in content)
    style_score = sum(1 for kw in style_keywords if kw in content)

    # If no clear match, use category
    if security_score > perf_score and security_score > style_score:
        return AGENT_SECURITY
    elif perf_score > style_score:
        return AGENT_PERFORMANCE
    elif style_score > 0:
        return AGENT_STYLE
    else:
        return AGENT_BUG


def _update_agent_results(
    deduplicated: list[Finding], agent_results: dict[str, Any]
) -> dict[str, Any]:
    """Rebuild agent_results to match deduplicated findings."""
    from src.models.finding import Category

    # Clear all findings
    for agent_name in agent_results:
        if isinstance(agent_results[agent_name], dict):
            agent_results[agent_name]["findings"] = []

    # Reassign findings to agents based on category
    for finding in deduplicated:
        category_to_agent = {
            Category.SECURITY: "security",
            Category.BUG: "bug_detection",
            Category.STYLE: "style",
            Category.PERFORMANCE: "performance",
        }

        agent_name = category_to_agent.get(finding.category, "bug_detection")

        if agent_name in agent_results and isinstance(agent_results[agent_name], dict):
            if "findings" not in agent_results[agent_name]:
                agent_results[agent_name]["findings"] = []
            agent_results[agent_name]["findings"].append(finding)

    return agent_results
