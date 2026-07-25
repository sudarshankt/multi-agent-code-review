"""Aggregation for the end-to-end finding-agent -> fix-agent pipeline evaluation."""

from __future__ import annotations

from eval.e2e_eval.models import PipelineCaseResult, PipelineMetrics
from eval.finding_eval.models import CaseResult, MatchedPair
from eval.finding_eval.scoring import DEFAULT_LINE_TOLERANCE, greedy_match
from eval.golden.models import ExpectedFinding
from src.models.finding import Finding


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def match_and_fix_inputs(
    file_path: str,
    expected: list[ExpectedFinding],
    actual: list[Finding],
    *,
    line_tolerance: int = DEFAULT_LINE_TOLERANCE,
) -> tuple[CaseResult, list[Finding]]:
    """Match a live finding-agent run against golden expected findings, and
    return both the usual CaseResult (for finding-stage precision/recall) and
    the matched actual Finding objects, so the fix agent runs on exactly what
    the finding agent produced -- not a golden-derived stand-in.
    """
    matched, missed, unmatched_actual = greedy_match(expected, actual, line_tolerance=line_tolerance)
    case = CaseResult(
        file=file_path,
        matched=[
            MatchedPair(
                expected=exp,
                actual_title=act.title,
                actual_description=act.description,
                actual_start_line=act.location.start_line,
                similarity=similarity,
            )
            for exp, act, similarity in matched
        ],
        missed=missed,
        unexpected=[act.title for act in unmatched_actual],
    )
    matched_findings = [act for _, act, _ in matched]
    return case, matched_findings


def aggregate_pipeline_metrics(agent_name: str, cases: list[PipelineCaseResult]) -> PipelineMetrics:
    finding_cases = [c.finding for c in cases]
    tp = sum(len(c.matched) for c in finding_cases)
    fp = sum(len(c.unexpected) for c in finding_cases)
    fn = sum(len(c.missed) for c in finding_cases)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    similarities = [pair.similarity for c in finding_cases for pair in c.matched]
    avg_similarity = round(sum(similarities) / len(similarities), 3) if similarities else 0.0

    attempted = [c for c in cases if c.fix_attempted]
    successes = [c for c in attempted if c.fix_success]
    syntax_checked = [c for c in attempted if c.syntax_valid is not None]
    syntax_valid = [c for c in syntax_checked if c.syntax_valid]
    judged = [c.judge for c in attempted if c.judge is not None]
    resolved = [j for j in judged if j.resolved]

    # A file only counts as pipeline-resolved if the finding agent surfaced
    # everything expected in it (no misses) AND the fix agent's output was
    # judged resolved. A file with any false negative can never be resolved
    # end-to-end, since the fix agent never saw the missed finding.
    files_with_expected = [c for c in cases if c.finding.matched or c.finding.missed]
    pipeline_resolved = [
        c
        for c in files_with_expected
        if not c.finding.missed and c.judge is not None and c.judge.resolved
    ]

    return PipelineMetrics(
        agent_name=agent_name,
        cases=len(cases),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
        avg_similarity=avg_similarity,
        fix_attempted=len(attempted),
        fix_success_rate=round(len(successes) / len(attempted), 3) if attempted else 0.0,
        syntax_valid_rate=round(len(syntax_valid) / len(syntax_checked), 3) if syntax_checked else 0.0,
        resolved_rate=round(len(resolved) / len(judged), 3) if judged else 0.0,
        pipeline_resolved_rate=(
            round(len(pipeline_resolved) / len(files_with_expected), 3) if files_with_expected else 0.0
        ),
        avg_correctness=_mean([j.correctness for j in judged]),
        avg_safety=_mean([j.safety for j in judged]),
        avg_minimality=_mean([j.minimality for j in judged]),
        avg_explanation_quality=_mean([j.explanation_quality for j in judged]),
        case_results=cases,
    )
