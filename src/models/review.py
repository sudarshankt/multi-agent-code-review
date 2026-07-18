"""Domain models for a review run."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.models.finding import Finding


class ReviewStatus(StrEnum):
    PENDING = "pending"
    FETCHING = "fetching"
    ANALYZING = "analyzing"
    FIXING = "fixing"
    TESTING = "testing"
    CREATING_PR = "creating_pr"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Statuses that terminate an SSE stream.
TERMINAL_STATUSES = {ReviewStatus.COMPLETED, ReviewStatus.FAILED, ReviewStatus.SKIPPED}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class PRInfo(BaseModel):
    owner: str
    repo: str
    pr_number: int
    title: str | None = None
    author: str | None = None
    head_branch: str | None = None
    base_branch: str | None = None
    head_sha: str | None = None
    html_url: str | None = None


class AgentResult(BaseModel):
    agent_name: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    findings: list[Finding] = Field(default_factory=list)
    duration_seconds: float | None = None
    error: str | None = None


class Review(BaseModel):
    id: str = Field(default_factory=_new_id)
    pr_info: PRInfo
    status: ReviewStatus = ReviewStatus.PENDING
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)
    agent_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    total_findings: int = 0
    total_fixes: int = 0
    fix_branch: str | None = None
    fix_pr_url: str | None = None
    triggered_by: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def touch(self) -> None:
        self.updated_at = _utcnow()
