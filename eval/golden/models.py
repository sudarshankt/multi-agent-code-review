"""Shared schema for eval/golden/manifest.json, used by both finding_eval and fix_eval."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpectedFinding(BaseModel):
    """One golden-set finding an agent is expected to surface."""

    description: str
    start_line: int
    end_line: int
    severity: str | None = None


class GoldenCase(BaseModel):
    """A single golden file and the findings expected for one agent."""

    file: str
    expected: list[ExpectedFinding] = Field(default_factory=list)
