"""Domain models for analysis findings and fixes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    SECURITY = "security"
    BUG = "bug_detection"
    STYLE = "style"
    PERFORMANCE = "performance"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingSource(str, Enum):
    LLM = "llm"  # Claude LLM generated
    AST_ANALYZER = "ast_analyzer"  # Python AST static analysis
    LINTER = "linter"  # Ruff or similar linter


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


class Location(BaseModel):
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    snippet: str | None = None


class Finding(BaseModel):
    id: str = Field(default_factory=_new_id)
    category: Category
    severity: Severity
    confidence: Confidence = Confidence.MEDIUM
    title: str
    description: str
    location: Location
    suggestion: str | None = None
    references: list[str] = Field(default_factory=list)
    cwe_id: str | None = None
    agent_name: str | None = None
    source: FindingSource = FindingSource.LLM  # Source of the finding (LLM, AST, linter)
    created_at: datetime = Field(default_factory=_utcnow)


class FixResult(BaseModel):
    id: str = Field(default_factory=_new_id)
    finding_id: str | None = None
    category: Category
    file_path: str
    original_code: str | None = None
    fixed_code: str | None = None
    commit_sha: str | None = None
    commit_message: str | None = None
    success: bool = False
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
