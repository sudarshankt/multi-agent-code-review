"""LangGraph node functions with SSE event publishing."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from src.agents.bug_detection.agent import BugDetectionAgent
from src.agents.deduplication import deduplicate_findings
from src.agents.fix.agent import FixAgent
from src.agents.orchestrator.state import PRReviewState
from src.agents.performance.agent import PerformanceAgent
from src.agents.security.agent import SecurityAgent
from src.agents.style.agent import StyleAgent
from src.core.constants import (
    AGENT_BUG,
    AGENT_PERFORMANCE,
    AGENT_SECURITY,
    AGENT_STYLE,
)
from src.core.logging import get_logger
from src.models.review import AgentResult, ReviewStatus

logger = get_logger(__name__)


async def _publish_event_async(review_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Publish SSE event asynchronously."""
    try:
        from src.api.endpoints.sse import publish_event
        await publish_event(review_id, event_type, data)
    except Exception as exc:
        logger.warning("sse_publish_failed", review_id=review_id, error=str(exc))


async def initialize(state: PRReviewState) -> dict[str, Any]:
    """Initialize the review state."""
    review_id = state.get("review_id", "unknown")
    await _publish_event_async(
        review_id,
        "stage_update",
        {"stage": "INITIALIZED", "status": ReviewStatus.FETCHING.value},
    )
    return {
        "status": ReviewStatus.FETCHING,
        "findings": [],
        "agent_results": {},
        "fix_results": [],
        "proposed_fixes": [],
        "errors": [],
        "files_bypassed": 0,
        "diffs": {},
    }


async def fetch_pr(state: PRReviewState) -> dict[str, Any]:
    """Fetch PR metadata (already done, but update status)."""
    review_id = state.get("review_id", "unknown")
    await _publish_event_async(
        review_id,
        "stage_update",
        {"stage": "PR_FETCHED", "status": ReviewStatus.ANALYZING.value, "files_count": len(state.get("files", {}))},
    )
    return {"status": ReviewStatus.ANALYZING, "diffs": state.get("diffs", {})}


async def check_success(state: PRReviewState) -> dict[str, Any]:
    """Check if we have the PR data we need."""
    if not state.get("pr_info") or not state.get("files"):
        return {"status": ReviewStatus.FAILED, "errors": ["Failed to fetch PR data"]}
    return {}


async def analyze_security(state: PRReviewState) -> dict[str, Any]:
    """Run SecurityAgent in parallel."""
    review_id = state.get("review_id", "unknown")
    started = time.monotonic()
    agent = SecurityAgent()
    context = {
        "triage_enabled": True,
        "diffs": state.get("diffs", {}),
        "files_bypassed": int(state.get("files_bypassed", 0)),
    }
    findings = await agent.run(state["files"], context)
    duration = time.monotonic() - started
    files_bypassed = int(context.get("files_bypassed", 0))
    logger.info(
        "agent_run_completed",
        agent_name=AGENT_SECURITY,
        review_id=review_id,
        findings_count=len(findings),
        files_bypassed=files_bypassed,
        duration_seconds=round(duration, 3),
    )
    await _publish_event_async(
        review_id,
        "agent_completed",
        {"agent": AGENT_SECURITY, "findings_count": len(findings), "duration_seconds": duration, "files_bypassed": files_bypassed},
    )
    return {
        "findings": findings,
        "files_bypassed": files_bypassed,
        "agent_results": {
            AGENT_SECURITY: AgentResult(
                agent_name=AGENT_SECURITY,
                status="completed",
                findings=findings,
                duration_seconds=duration,
            ).model_dump()
        },
    }


async def analyze_bug(state: PRReviewState) -> dict[str, Any]:
    """Run BugDetectionAgent in parallel."""
    review_id = state.get("review_id", "unknown")
    started = time.monotonic()
    agent = BugDetectionAgent()
    context = {
        "triage_enabled": True,
        "diffs": state.get("diffs", {}),
        "files_bypassed": int(state.get("files_bypassed", 0)),
    }
    findings = await agent.run(state["files"], context)
    duration = time.monotonic() - started
    files_bypassed = int(context.get("files_bypassed", 0))
    logger.info(
        "agent_run_completed",
        agent_name=AGENT_BUG,
        review_id=review_id,
        findings_count=len(findings),
        files_bypassed=files_bypassed,
        duration_seconds=round(duration, 3),
    )
    await _publish_event_async(
        review_id,
        "agent_completed",
        {"agent": AGENT_BUG, "findings_count": len(findings), "duration_seconds": duration, "files_bypassed": files_bypassed},
    )
    return {
        "findings": findings,
        "files_bypassed": files_bypassed,
        "agent_results": {
            AGENT_BUG: AgentResult(
                agent_name=AGENT_BUG,
                status="completed",
                findings=findings,
                duration_seconds=duration,
            ).model_dump()
        },
    }


async def analyze_style(state: PRReviewState) -> dict[str, Any]:
    """Run StyleAgent in parallel."""
    review_id = state.get("review_id", "unknown")
    started = time.monotonic()
    agent = StyleAgent()
    context = {
        "triage_enabled": True,
        "diffs": state.get("diffs", {}),
        "files_bypassed": int(state.get("files_bypassed", 0)),
    }
    findings = await agent.run(state["files"], context)
    duration = time.monotonic() - started
    files_bypassed = int(context.get("files_bypassed", 0))
    logger.info(
        "agent_run_completed",
        agent_name=AGENT_STYLE,
        review_id=review_id,
        findings_count=len(findings),
        files_bypassed=files_bypassed,
        duration_seconds=round(duration, 3),
    )
    await _publish_event_async(
        review_id,
        "agent_completed",
        {"agent": AGENT_STYLE, "findings_count": len(findings), "duration_seconds": duration, "files_bypassed": files_bypassed},
    )
    return {
        "findings": findings,
        "files_bypassed": files_bypassed,
        "agent_results": {
            AGENT_STYLE: AgentResult(
                agent_name=AGENT_STYLE,
                status="completed",
                findings=findings,
                duration_seconds=duration,
            ).model_dump()
        },
    }


async def analyze_performance(state: PRReviewState) -> dict[str, Any]:
    """Run PerformanceAgent in parallel."""
    review_id = state.get("review_id", "unknown")
    started = time.monotonic()
    agent = PerformanceAgent()
    context = {
        "triage_enabled": True,
        "diffs": state.get("diffs", {}),
        "files_bypassed": int(state.get("files_bypassed", 0)),
    }
    findings = await agent.run(state["files"], context)
    duration = time.monotonic() - started
    files_bypassed = int(context.get("files_bypassed", 0))
    logger.info(
        "agent_run_completed",
        agent_name=AGENT_PERFORMANCE,
        review_id=review_id,
        findings_count=len(findings),
        files_bypassed=files_bypassed,
        duration_seconds=round(duration, 3),
    )
    await _publish_event_async(
        review_id,
        "agent_completed",
        {"agent": AGENT_PERFORMANCE, "findings_count": len(findings), "duration_seconds": duration, "files_bypassed": files_bypassed},
    )
    return {
        "findings": findings,
        "files_bypassed": files_bypassed,
        "agent_results": {
            AGENT_PERFORMANCE: AgentResult(
                agent_name=AGENT_PERFORMANCE,
                status="completed",
                findings=findings,
                duration_seconds=duration,
            ).model_dump()
        },
    }


async def aggregate_findings(state: PRReviewState) -> dict[str, Any]:
    """Sync point after parallel agents; deduplicate and aggregate results."""
    review_id = state.get("review_id", "unknown")
    findings = state.get("findings", [])
    agent_results = state.get("agent_results", {})

    # Deduplicate similar findings across agents
    deduplicated_findings, updated_results = deduplicate_findings(findings, agent_results)

    # Log deduplication summary
    if len(deduplicated_findings) < len(findings):
        removed_count = len(findings) - len(deduplicated_findings)
        logger.info(
            "findings_deduplicated",
            original_count=len(findings),
            deduplicated_count=len(deduplicated_findings),
            removed_count=removed_count,
        )

    next_status = ReviewStatus.FIXING if deduplicated_findings else ReviewStatus.COMPLETED
    await _publish_event_async(
        review_id,
        "stage_update",
        {
            "stage": "ANALYSIS_COMPLETE",
            "total_findings": len(deduplicated_findings),
            "deduplicated_from": len(findings),
            "status": next_status.value,
        },
    )
    return {
        "status": next_status,
        "findings": deduplicated_findings,
        "agent_results": updated_results,
        "files_bypassed": state.get("files_bypassed", 0),
    }


async def should_apply_fixes(state: PRReviewState) -> str:
    """Conditional: proceed to fixes if any findings exist."""
    findings = state.get("findings", [])
    if not findings:
        return "skip_fixes"
    return "apply_fixes"


async def apply_fixes(state: PRReviewState) -> dict[str, Any]:
    """Generate fix proposals (no commit). Proposals are stored for human review."""
    review_id = state.get("review_id", "unknown")
    findings = state.get("findings", [])
    files = state["files"]

    await _publish_event_async(
        review_id,
        "stage_update",
        {"stage": "GENERATING_PROPOSALS", "status": ReviewStatus.FIXING.value},
    )

    agent = FixAgent()
    proposals = await agent.generate_proposals(files, findings, review_id=review_id)

    # Stream each proposal to the UI via SSE so the diff viewer populates in real-time
    for proposal in proposals:
        await _publish_event_async(
            review_id,
            "proposed_fix",
            {
                "fix_id": proposal.id,
                "category": proposal.category,
                "file_path": proposal.file_path,
                "diff": proposal.diff,
                "explanation": proposal.explanation,
                "status": proposal.status.value,
                "finding_ids": proposal.finding_ids,
            },
        )

    logger.info(
        "proposals_generated",
        review_id=review_id,
        proposals_count=len(proposals),
    )

    await _publish_event_async(
        review_id,
        "stage_update",
        {
            "stage": "PROPOSALS_READY",
            "proposals_count": len(proposals),
            "status": ReviewStatus.FIXING.value,
        },
    )

    return {"proposed_fixes": proposals, "fix_results": [], "status": ReviewStatus.FIXING}


async def finalize(state: PRReviewState) -> dict[str, Any]:
    """Final aggregation and logging."""
    review_id = state.get("review_id", "unknown")
    findings = state.get("findings", [])
    proposed_fixes = state.get("proposed_fixes", [])

    await _publish_event_async(
        review_id,
        "stage_update",
        {
            "stage": "COMPLETED",
            "status": ReviewStatus.COMPLETED.value,
            "total_findings": len(findings),
            "proposals_pending_review": len(proposed_fixes),
        },
    )

    logger.info(
        "review_complete",
        pr_number=state["pr_info"].pr_number,
        total_findings=len(findings),
        proposals_pending_review=len(proposed_fixes),
    )
    return {"status": ReviewStatus.COMPLETED}
