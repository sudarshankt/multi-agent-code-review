from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models.finding import Category, Finding
from src.models.review import Review


def load_review_from_json(path: str | Path) -> Review:
    """Load a saved review payload produced by the app into the project Review model."""
    review_path = Path(path)
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    return Review.model_validate(payload)


def summarize_findings(review: Review) -> dict[str, Any]:
    """Summarize findings from the review model into evaluation-friendly fields."""
    by_agent: dict[str, list[Finding]] = {}
    for agent_name, agent_result in review.agent_results.items():
        by_agent[agent_name] = list(agent_result.findings)

    security_labels = [1 if any(f.category == Category.SECURITY for f in findings) else 0 for findings in by_agent.values()]
    bug_labels = [1 if any(f.category == Category.BUG for f in findings) else 0 for findings in by_agent.values()]

    input_file_count = 0
    input_files_bypassed = 0
    for payload in review.agent_inputs.values():
        files = payload.get("files") or {}
        if isinstance(files, dict):
            input_file_count += len(files)
        context = payload.get("context") or {}
        if isinstance(context, dict):
            input_files_bypassed = max(input_files_bypassed, int(context.get("files_bypassed", 0)))

    ordered_agents = list(by_agent.keys()) if by_agent else list(review.agent_inputs.keys())

    return {
        "agents": ordered_agents,
        "agent_count": len(by_agent),
        "input_agent_count": len(review.agent_inputs),
        "input_file_count": input_file_count,
        "input_files_bypassed": input_files_bypassed,
        "security_labels": security_labels,
        "bug_labels": bug_labels,
        "total_findings": review.total_findings,
    }
