"""Fuzzy matching of agent findings against a golden dataset.

LLM findings don't line up with golden findings exactly, so matching is done
per-file by category, treating two findings as the same issue when their line
ranges overlap (within a small tolerance). Severity is not required to match
by default since agents may reasonably disagree on severity tier while still
correctly identifying the underlying issue.
"""

from __future__ import annotations

import difflib
import os
from functools import lru_cache

import numpy as np

from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.finding import Finding

from eval.finding_eval.models import AgentMetrics, CaseResult, MatchedPair
from eval.golden.models import ExpectedFinding

logger = get_logger(__name__)

DEFAULT_LINE_TOLERANCE = 2

_tokenizer = None
_session = None
_model_load_attempted = False


def _get_model():
    """Lazily load the local ONNX embedding model (no network call, no torch)."""
    global _tokenizer, _session, _model_load_attempted
    if _model_load_attempted:
        return _tokenizer, _session
    _model_load_attempted = True
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_dir = get_settings().eval_embedding_model_path
        _tokenizer = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        _tokenizer.enable_padding()
        _tokenizer.enable_truncation(max_length=256)
        _session = ort.InferenceSession(
            os.path.join(model_dir, "model.onnx"), providers=["CPUExecutionProvider"]
        )
    except ImportError:
        logger.warning(
            "onnx_embedding_deps_not_installed",
            hint="Install with: pip install -e '.[eval]'; falling back to difflib similarity",
        )
    except Exception as exc:
        logger.error("embedding_model_load_failed", error=str(exc))
    return _tokenizer, _session


@lru_cache(maxsize=None)
def _embed(text: str):
    tokenizer, session = _get_model()
    if session is None:
        return None
    encoding = tokenizer.encode(text)
    input_ids = np.array([encoding.ids], dtype=np.int64)
    attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)
    outputs = session.run(
        None,
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )
    token_embeddings = outputs[0][0]  # (seq, hidden)
    mask = attention_mask[0][:, None].astype(np.float32)
    mean_pooled = (token_embeddings * mask).sum(axis=0) / np.clip(mask.sum(), 1e-9, None)
    return mean_pooled / np.linalg.norm(mean_pooled)


def _text_similarity(a: str, b: str) -> float:
    """Cosine similarity in [0, 1] between embeddings of two finding descriptions.

    Falls back to character-level SequenceMatcher if the optional `rag` extra
    (sentence-transformers) isn't installed.
    """
    a_norm, b_norm = a.strip().lower(), b.strip().lower()
    vec_a, vec_b = _embed(a_norm), _embed(b_norm)
    if vec_a is None or vec_b is None:
        return round(difflib.SequenceMatcher(None, a_norm, b_norm).ratio(), 3)
    # Embeddings are normalized, so dot product is cosine similarity; clamp for float drift.
    similarity = max(0.0, min(1.0, float(vec_a @ vec_b)))
    return round(similarity, 3)


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


def greedy_match(
    expected: list[ExpectedFinding],
    actual: list[Finding],
    *,
    line_tolerance: int = DEFAULT_LINE_TOLERANCE,
) -> tuple[list[tuple[ExpectedFinding, Finding, float]], list[ExpectedFinding], list[Finding]]:
    """Greedily pair expected findings to actual findings by line overlap,
    breaking ties by description similarity.

    Returns (matched triples of (expected, actual, similarity), missed expected
    findings, unmatched actual findings). Factored out of match_case so other
    evals (e.g. e2e_eval) can get the matched Finding objects themselves rather
    than just the text fields match_case's MatchedPair keeps.
    """
    unmatched_actual = list(actual)
    matched: list[tuple[ExpectedFinding, Finding, float]] = []
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
            matched.append((exp, act, best_similarity))

    return matched, missed, unmatched_actual


def match_case(
    file_path: str,
    expected: list[ExpectedFinding],
    actual: list[Finding],
    *,
    line_tolerance: int = DEFAULT_LINE_TOLERANCE,
) -> CaseResult:
    """Greedily match expected findings to actual findings for one file."""
    matched, missed, unmatched_actual = greedy_match(expected, actual, line_tolerance=line_tolerance)
    return CaseResult(
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
