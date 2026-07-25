"""Domain models for the fix-agent LLM-as-judge evaluation."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ModelCandidate(BaseModel):
    """One generator model/provider configuration to evaluate."""

    label: str
    model_provider: str
    primary_model: str


class JudgeScore(BaseModel):
    """A judge LLM's rubric scores for one fix.

    correctness/safety/minimality/explanation_quality are all 0-1 floats
    (see src/prompts/templates/fix_judge.j2), so every metric in this eval
    sits on the same 0-1 scale.
    """

    resolved: bool
    correctness: float
    safety: float
    minimality: float
    explanation_quality: float
    regression_risk: str = "unknown"
    notes: str = ""


class FixCaseResult(BaseModel):
    """Outcome of running one model candidate's fix on one golden case."""

    model_label: str
    file: str
    category: str
    success: bool
    syntax_valid: bool | None = None
    error: str | None = None
    judge: JudgeScore | None = None


class ModelMetrics(BaseModel):
    model_label: str
    cases: int
    success_rate: float
    syntax_valid_rate: float
    resolved_rate: float
    avg_correctness: float
    avg_safety: float
    avg_minimality: float
    avg_explanation_quality: float
    case_results: list[FixCaseResult] = Field(default_factory=list)


class FixEvalReport(BaseModel):
    generated_at: datetime = Field(default_factory=_utcnow)
    models: list[ModelMetrics] = Field(default_factory=list)
