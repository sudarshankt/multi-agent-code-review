"""Domain models for the finding-agent evaluation matrix."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from eval.golden.models import ExpectedFinding


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MatchedPair(BaseModel):
    expected: ExpectedFinding
    actual_title: str
    actual_description: str = ""
    actual_start_line: int | None = None
    similarity: float = 0.0  # text similarity between expected.description and actual_description, 0-1


class CaseResult(BaseModel):
    """Match outcome for a single golden file."""

    file: str
    matched: list[MatchedPair] = Field(default_factory=list)
    missed: list[ExpectedFinding] = Field(default_factory=list)
    unexpected: list[str] = Field(default_factory=list)  # titles of unmatched actual findings


class AgentMetrics(BaseModel):
    agent_name: str
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    avg_similarity: float = 0.0  # mean text similarity across matched findings
    cases: list[CaseResult] = Field(default_factory=list)


class EvalReport(BaseModel):
    generated_at: datetime = Field(default_factory=_utcnow)
    agents: list[AgentMetrics] = Field(default_factory=list)
