"""Aggregation of per-case fix-agent judge scores into per-model metrics."""

from __future__ import annotations

from eval.fix_eval.models import FixCaseResult, ModelMetrics


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def aggregate_model_metrics(model_label: str, cases: list[FixCaseResult]) -> ModelMetrics:
    total = len(cases)
    successes = [c for c in cases if c.success]
    syntax_checked = [c for c in cases if c.syntax_valid is not None]
    syntax_valid = [c for c in syntax_checked if c.syntax_valid]
    judged = [c.judge for c in cases if c.judge is not None]
    resolved = [j for j in judged if j.resolved]

    return ModelMetrics(
        model_label=model_label,
        cases=total,
        success_rate=round(len(successes) / total, 3) if total else 0.0,
        syntax_valid_rate=round(len(syntax_valid) / len(syntax_checked), 3) if syntax_checked else 0.0,
        resolved_rate=round(len(resolved) / len(judged), 3) if judged else 0.0,
        avg_correctness=_mean([j.correctness for j in judged]),
        avg_safety=_mean([j.safety for j in judged]),
        avg_minimality=_mean([j.minimality for j in judged]),
        avg_explanation_quality=_mean([j.explanation_quality for j in judged]),
        case_results=cases,
    )
