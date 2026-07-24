"""Fuzzy matching of agent findings against a golden dataset.

LLM findings don't line up with golden findings exactly, so matching is done
per-file by category, treating two findings as the same issue when their line
ranges overlap (within a small tolerance). Severity is not required to match
by default since agents may reasonably disagree on severity tier while still
correctly identifying the underlying issue.
"""

from __future__ import annotations

import difflib

from src.models.finding import Finding

from eval.finding_eval.models import AgentMetrics, CaseResult, MatchedPair
from eval.golden.models import ExpectedFinding

DEFAULT_LINE_TOLERANCE = 2


def _text_similarity(a: str, b: str) -> float:
    """Ratio in [0, 1] of how similar two finding descriptions are."""
    return round(difflib.SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio(), 3)


def _overlaps(
    actual_start: int | None,
    actual_end: int | None,
    expected_start: int,
    expected_end: int,
    tolerance: int,
) -> bool:
    if actual_start is None:
        return False
    actual_end = actual_end if actual_end is not None else actual_start
    return (actual_start - tolerance) <= expected_end and (actual_end + tolerance) >= expected_start


def match_case(
    file_path: str,
    expected: list[ExpectedFinding],
    actual: list[Finding],
    *,
    line_tolerance: int = DEFAULT_LINE_TOLERANCE,
) -> CaseResult:
    """Greedily match expected findings to actual findings for one file."""
    unmatched_actual = list(actual)
    matched: list[MatchedPair] = []
    missed: list[ExpectedFinding] = []

    for exp in expected:
        best_idx: int | None = None
        best_similarity = -1.0
        for idx, act in enumerate(unmatched_actual):
            if not _overlaps(
                act.location.start_line,
                act.location.end_line,
                exp.start_line,
                exp.end_line,
                line_tolerance,
            ):
                continue
            # Among overlapping candidates, prefer the one whose description reads
            # most like the expected finding rather than just the first overlap.
            similarity = _text_similarity(exp.description, act.description)
            if similarity > best_similarity:
                best_similarity = similarity
                best_idx = idx
        if best_idx is None:
            missed.append(exp)
        else:
            act = unmatched_actual.pop(best_idx)
            matched.append(
                MatchedPair(
                    expected=exp,
                    actual_title=act.title,
                    actual_description=act.description,
                    actual_start_line=act.location.start_line,
                    similarity=best_similarity,
                )
            )

    unexpected = [act.title for act in unmatched_actual]
    return CaseResult(file=file_path, matched=matched, missed=missed, unexpected=unexpected)


def aggregate_metrics(agent_name: str, cases: list[CaseResult]) -> AgentMetrics:
    tp = sum(len(c.matched) for c in cases)
    fp = sum(len(c.unexpected) for c in cases)
    fn = sum(len(c.missed) for c in cases)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    similarities = [pair.similarity for c in cases for pair in c.matched]
    avg_similarity = round(sum(similarities) / len(similarities), 3) if similarities else 0.0

    return AgentMetrics(
        agent_name=agent_name,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
        avg_similarity=avg_similarity,
        cases=cases,
    )
