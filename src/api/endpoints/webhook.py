"""GitHub webhook endpoint."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from src.core.exceptions import WebhookValidationError
from src.core.logging import get_logger
from src.models.review import PRInfo, Review

logger = get_logger(__name__)

router = APIRouter()

# In-memory review storage (shared with review.py in main.py).
_reviews: dict[str, Review] = {}


@router.post("/webhook/github")
async def github_webhook(request: Request) -> dict[str, str]:
    """GitHub webhook endpoint. Receives pull_request events and enqueues reviews."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    event_type = request.headers.get("x-github-event", "")
    if event_type != "pull_request":
        return {"status": "ignored", "reason": f"Not a pull_request event ({event_type})"}

    action = body.get("action")
    if action not in {"opened", "synchronize", "reopened"}:
        return {"status": "ignored", "reason": f"Action not actionable ({action})"}

    try:
        pr = body.get("pull_request", {})
        owner = (body.get("repository") or {}).get("owner", {}).get("login")
        repo = (body.get("repository") or {}).get("name")
        pr_number = pr.get("number")

        if not all([owner, repo, pr_number]):
            raise WebhookValidationError("Missing owner, repo, or pr_number in webhook")

        # Create review record.
        pr_info = PRInfo(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            title=pr.get("title"),
            author=(pr.get("user") or {}).get("login"),
            head_branch=(pr.get("head") or {}).get("ref"),
            base_branch=(pr.get("base") or {}).get("ref"),
            head_sha=(pr.get("head") or {}).get("sha"),
            html_url=pr.get("html_url"),
        )
        review = Review(pr_info=pr_info, triggered_by="webhook")
        _reviews[review.id] = review

        # Queue the review (MVP: in-process task; prod would enqueue to Redis/ARQ).
        from src.api.endpoints.review import _run_review

        asyncio.create_task(_run_review(review.id))

        logger.info(
            "webhook_enqueued",
            review_id=review.id,
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            action=action,
        )
        return {"status": "accepted", "review_id": review.id}

    except WebhookValidationError as exc:
        logger.warning("webhook_validation_failed", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("webhook_processing_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to process webhook") from exc
