"""Domain models for the end-to-end (finding agent -> fix agent) pipeline evaluation."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from eval.finding_eval.models import CaseResult
from eval.fix_eval.models import JudgeScore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineCaseResult(BaseModel):
    """Finding-stage match plus fix-stage outcome for one golden file.

    fix_attempted is False whenever the finding agent produced nothing that
    matched a golden finding for this file -- there was nothing to hand the
    fix agent.
    """

    finding: CaseResult
    fix_attempted: bool = False
    fix_success: bool = False
    syntax_valid: bool | None = None
    fix_error: str | None = None
    judge: JudgeScore | None = None


class PipelineMetrics(BaseModel):
    agent_name: str
    cases: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    avg_similarity: float = 0.0
    fix_attempted: int
    fix_success_rate: float
    syntax_valid_rate: float
    resolved_rate: float  # judge.resolved rate, among fix attempts that were judged
    pipeline_resolved_rate: float  # end-to-end: found (fully) AND fixed AND judged resolved
    avg_correctness: float
    avg_safety: float
    avg_minimality: float
    avg_explanation_quality: float
    case_results: list[PipelineCaseResult] = Field(default_factory=list)


class E2EReport(BaseModel):
    generated_at: datetime = Field(default_factory=_utcnow)
    agents: list[PipelineMetrics] = Field(default_factory=list)
