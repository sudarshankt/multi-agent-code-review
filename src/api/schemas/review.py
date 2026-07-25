"""Request/response schemas for the review API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.finding import Finding
from src.models.fix import ProposedFix
from src.models.review import ReviewStatus


class CreateReviewRequest(BaseModel):
    """POST /reviews request: either pr_url or (owner, repo, pr_number)."""

    pr_url: str | None = None
    owner: str | None = None
    repo: str | None = None
    pr_number: int | None = None


class ReviewResponse(BaseModel):
    """Review summary for list/detail endpoints."""

    id: str
    status: ReviewStatus
    pr_number: int
    pr_title: str | None = None
    total_findings: int = 0
    total_fixes: int = 0
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ReviewDetailResponse(BaseModel):
    """Full review with findings grouped by category."""

    id: str
    status: ReviewStatus
    pr_number: int
    pr_title: str | None = None
    pr_author: str | None = None
    pr_url: str | None = None
    pr_head_branch: str | None = None
    findings_by_category: dict[str, list[Finding]] = Field(default_factory=dict)
    proposed_fixes: list[ProposedFix] = Field(default_factory=list)
    total_findings: int = 0
    total_fixes: int = 0
    fix_branch: str | None = None
    fix_pr_url: str | None = None
    fix_commit_url: str | None = None
    fix_commits: dict[str, str] = Field(default_factory=dict)
    fix_severity_levels: list[str] = Field(default_factory=list)
    analysis_duration_seconds: float | None = None
    total_duration_seconds: float | None = None
    tokens_used: int = 0
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ListReviewsResponse(BaseModel):
    """Paginated list of reviews."""

    items: list[ReviewResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    environment: str
    version: str
