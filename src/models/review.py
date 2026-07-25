"""Domain models for a review run."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from src.models.finding import Finding
from src.models.fix import FixStatus, ProposedFix, TestRunSummary


class ReviewStatus(str, Enum):
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
    return datetime.now(timezone.utc)


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
    base_sha: str | None = None
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
    total_findings: int = 0
    total_fixes: int = 0
    fix_branch: str | None = None
    fix_pr_url: str | None = None  # commit URL after fixes applied
    fix_commits: dict[str, str] = Field(default_factory=dict)  # {category: commit_sha}
    fix_severity_levels: list[str] = Field(default_factory=list)  # which severities were fixed
    triggered_by: str | None = None
    error_message: str | None = None
    proposed_fixes: list[ProposedFix] = Field(default_factory=list)
    test_run: TestRunSummary | None = None
    # Files from the PR (for fix generation)
    files: dict[str, str] = Field(default_factory=dict)  # {file_path: file_content}
    # Timing tracking
    analysis_started: datetime | None = None
    analysis_completed: datetime | None = None
    fixes_applied_at: datetime | None = None
    tokens_used: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def touch(self) -> None:
        self.updated_at = _utcnow()

    @property
    def analysis_duration_seconds(self) -> float | None:
        if self.analysis_started and self.analysis_completed:
            return (self.analysis_completed - self.analysis_started).total_seconds()
        return None

    @property
    def total_duration_seconds(self) -> float | None:
        if self.created_at and self.completed_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None

    @property
    def pending_fix_count(self) -> int:
        return sum(1 for f in self.proposed_fixes if f.status == FixStatus.PENDING)

    @property
    def approved_fix_count(self) -> int:
        return sum(1 for f in self.proposed_fixes if f.status == FixStatus.APPROVED)

    @property
    def committed_fix_count(self) -> int:
        return sum(1 for f in self.proposed_fixes if f.status == FixStatus.COMMITTED)
