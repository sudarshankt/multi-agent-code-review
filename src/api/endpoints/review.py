"""Review API endpoints."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api.schemas.review import (
    CreateReviewRequest,
    ListReviewsResponse,
    ReviewDetailResponse,
    ReviewResponse,
)
from src.core.config import get_settings
from src.core.constants import SOURCE_EXTENSIONS
from src.core.logging import get_logger
from src.models.review import PRInfo, Review, ReviewStatus
from src.services.artifact_service import persist_generated_artifacts
from src.services.github_service import GitHubService

logger = get_logger(__name__)

router = APIRouter()

# In-memory review storage (MVP). In production, use a real database.
_reviews: dict[str, Review] = {}


def _is_eligible_source_file(path: str, ignore_paths: list[str]) -> bool:
    if not path.endswith(SOURCE_EXTENSIONS):
        return False
    normalized = path.lower()
    return not any(normalized.startswith(prefix.lower()) for prefix in ignore_paths)


def _parse_pr_url(url: str) -> tuple[str, str, int] | None:
    """Parse GitHub PR URL. Handles https://github.com/{owner}/{repo}/pull/{pr_number}."""
    # Regex to extract owner, repo, pr_number from a GitHub PR URL.
    pattern = r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.match(pattern, url)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    return None


async def _run_review(review_id: str) -> None:
    """Background task: run the review pipeline (orchestrator)."""
    review = _reviews.get(review_id)
    if not review:
        return

    try:
        from src.agents.orchestrator import get_graph
        from src.api.endpoints.sse import publish_event

        review.status = ReviewStatus.ANALYZING
        await publish_event(review_id, "status_update", {"status": review.status.value})

        # Fetch PR data if not already done.
        if not review.pr_info.head_sha:
            async with GitHubService() as gh:
                pr_data = await gh.fetch_pr_data(
                    review.pr_info.owner,
                    review.pr_info.repo,
                    review.pr_info.pr_number,
                )
                pr_info = pr_data["pr_info"]
                files = pr_data["files"]
                diffs = pr_data.get("diffs", {})
                review.pr_info = pr_info
        else:
            files = {}  # Already have files from initial fetch.
            diffs = {}

        # Run the orchestrator graph.
        graph = get_graph()
        review.agent_inputs = {
            "security": {
                "files": files,
                "context": {"triage_enabled": True, "diffs": diffs, "files_bypassed": 0},
            },
            "bug_detection": {
                "files": files,
                "context": {"triage_enabled": True, "diffs": diffs, "files_bypassed": 0},
            },
            "style": {
                "files": files,
                "context": {"triage_enabled": True, "diffs": diffs, "files_bypassed": 0},
            },
            "performance": {
                "files": files,
                "context": {"triage_enabled": True, "diffs": diffs, "files_bypassed": 0},
            },
        }

        input_state = {
            "pr_info": review.pr_info,
            "files": files,
            "diffs": diffs,
            "review_id": review_id,
            "status": ReviewStatus.ANALYZING,
            "findings": [],
            "agent_results": {},
            "fix_results": [],
            "errors": [],
            "files_bypassed": 0,
        }
        result = await graph.ainvoke(input_state)

        # Update review with results.
        findings = result.get("findings", [])
        agent_results = result.get("agent_results", {})
        fix_results = result.get("fix_results", [])

        # Populate agent_results grouped by category (bug #7).
        for agent_name, agent_result_dict in agent_results.items():
            if isinstance(agent_result_dict, dict):
                from src.models.review import AgentResult

                review.agent_results[agent_name] = AgentResult(**agent_result_dict)

        review.total_findings = len(findings)
        review.total_fixes = len([r for r in fix_results if r.success])
        files_bypassed = int(result.get("files_bypassed", 0))
        persist_generated_artifacts(review.id, fix_results)
        for agent_input in review.agent_inputs.values():
            context = agent_input.get("context")
            if isinstance(context, dict):
                context["files_bypassed"] = files_bypassed
        review.status = ReviewStatus.COMPLETED

        # Set fix PR URL to the original PR (fixes committed to same branch)
        if review.total_fixes > 0 and review.pr_info.html_url:
            review.fix_pr_url = review.pr_info.html_url

        await publish_event(review_id, "status_update", {"status": review.status.value})
        logger.info(
            "review_completed",
            pr=f"{review.pr_info.owner}/{review.pr_info.repo}#{review.pr_info.pr_number}",
            findings=review.total_findings,
            fixes=review.total_fixes,
            fix_pr_url=review.fix_pr_url,
        )

    except Exception as exc:  # noqa: BLE001 - catch all, mark as failed
        review.status = ReviewStatus.FAILED
        review.error_message = str(exc)
        logger.error("review_failed", review_id=review_id, error=str(exc))
        await publish_event(review_id, "status_update", {"status": review.status.value})


@router.post("/reviews", status_code=202)
async def create_review(req: CreateReviewRequest) -> ReviewResponse:
    """
    Create a PR review. Accepts pr_url or (owner, repo, pr_number).
    Returns 202 (Accepted); runs the review in the background.
    """
    owner = req.owner
    repo = req.repo
    pr_number = req.pr_number

    if req.pr_url:
        parsed = _parse_pr_url(req.pr_url)
        if not parsed:
            raise HTTPException(
                status_code=400,
                detail="Invalid PR URL format. Expected https://github.com/{owner}/{repo}/pull/{pr_number}",
            )
        owner, repo, pr_number = parsed

    if not (owner and repo and pr_number):
        raise HTTPException(
            status_code=400,
            detail="Provide either pr_url or (owner, repo, pr_number)",
        )

    # Create the review record.
    pr_info = PRInfo(owner=owner, repo=repo, pr_number=pr_number)
    review = Review(pr_info=pr_info, triggered_by="api")
    _reviews[review.id] = review

    settings = get_settings()
    try:
        async with GitHubService() as gh:
            changed_files = await gh.get_pr_files(owner, repo, pr_number)
    except Exception as exc:  # noqa: BLE001 - do not block review creation on preflight issues
        logger.warning(
            "preflight_fetch_failed",
            review_id=review.id,
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            error=str(exc),
        )
    else:
        relevant_files = [
            entry.get("filename", "")
            for entry in changed_files
            if isinstance(entry, dict)
            and entry.get("status") != "removed"
            and _is_eligible_source_file(entry.get("filename", ""), settings.ignore_paths)
        ]
        if len(relevant_files) > settings.max_files_per_pr:
            review.status = ReviewStatus.SKIPPED
            review.error_message = (
                f"AI review skipped: PR exceeds the maximum file limit ({settings.max_files_per_pr})."
            )
            review.touch()
            logger.info(
                "review_skipped_large_pr",
                review_id=review.id,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                files=len(relevant_files),
                limit=settings.max_files_per_pr,
            )
            return ReviewResponse(
                id=review.id,
                status=review.status,
                pr_number=review.pr_info.pr_number,
                pr_title=review.pr_info.title,
                total_findings=review.total_findings,
                total_fixes=review.total_fixes,
                created_at=review.created_at,
                updated_at=review.updated_at,
                completed_at=review.completed_at,
            )

    # Kick off the background task (no await).
    asyncio.create_task(_run_review(review.id))

    logger.info(
        "review_created",
        review_id=review.id,
        owner=owner,
        repo=repo,
        pr_number=pr_number,
    )
    return ReviewResponse(
        id=review.id,
        status=review.status,
        pr_number=review.pr_info.pr_number,
        pr_title=review.pr_info.title,
        total_findings=review.total_findings,
        total_fixes=review.total_fixes,
        created_at=review.created_at,
        updated_at=review.updated_at,
        completed_at=review.completed_at,
    )


@router.get("/reviews", response_model=ListReviewsResponse)
async def list_reviews(page: int = 1, page_size: int = 20) -> ListReviewsResponse:
    """List all reviews (paginated)."""
    all_reviews = list(_reviews.values())
    total = len(all_reviews)
    start = (page - 1) * page_size
    end = start + page_size
    items = all_reviews[start:end]

    return ListReviewsResponse(
        items=[
            ReviewResponse(
                id=r.id,
                status=r.status,
                pr_number=r.pr_info.pr_number,
                pr_title=r.pr_info.title,
                total_findings=r.total_findings,
                total_fixes=r.total_fixes,
                created_at=r.created_at,
                updated_at=r.updated_at,
                completed_at=r.completed_at,
            )
            for r in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/reviews/{review_id}", response_model=ReviewDetailResponse)
async def get_review(review_id: str) -> ReviewDetailResponse:
    """Get a review by ID with full findings."""
    review = _reviews.get(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Group findings by category (bug #7).
    by_category: dict[str, list[Any]] = {}
    for agent_result in review.agent_results.values():
        if isinstance(agent_result, dict):
            category = agent_result.get("agent_name", "unknown")
            findings = agent_result.get("findings", [])
            by_category[category] = findings
        else:
            category = agent_result.agent_name
            by_category[category] = agent_result.findings

    return ReviewDetailResponse(
        id=review.id,
        status=review.status,
        pr_number=review.pr_info.pr_number,
        pr_title=review.pr_info.title,
        pr_author=review.pr_info.author,
        findings_by_category=by_category,
        total_findings=review.total_findings,
        total_fixes=review.total_fixes,
        fix_pr_url=review.fix_pr_url,
        created_at=review.created_at,
        updated_at=review.updated_at,
        completed_at=review.completed_at,
    )
