"""Classification metrics shared by the security/bug/patch/style runners.

Per Section 4 of the instructions doc:
  - Precision/Recall/F1 at the function level (vulnerable vs not, buggy vs not)
  - Patch Pass Rate with a test-file-tamper check
  - PEP8 Agreement vs a Pylint self-baseline, with false-positive rate
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PRF1:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int

    def as_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "confusion": {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn},
        }


def precision_recall_f1(y_true: list[int], y_pred: list[int]) -> PRF1:
    """Binary precision/recall/F1. y_true/y_pred are 0/1 lists of equal length.

    No sklearn dependency required — this is intentionally dependency-light
    so it doesn't block a runner from executing if sklearn isn't installed
    in a given environment.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"length mismatch: {len(y_true)} vs {len(y_pred)}")
    if not y_true:
        return PRF1(0.0, 0.0, 0.0, 0, 0, 0, 0)

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return PRF1(precision, recall, f1, tp, fp, fn, tn)


@dataclass
class PatchEvalResult:
    passed: bool
    tampered_tests: bool  # True if the patch touched test files (red flag)


def patch_pass_rate(results: list[PatchEvalResult]) -> dict:
    """Fraction of patches that pass tests AND don't tamper with the test
    files themselves (Section 4: "does not just delete/weaken the failing
    test").
    """
    if not results:
        return {"pass_rate": 0.0, "n": 0, "tampered_count": 0, "clean_pass_rate": 0.0}

    n = len(results)
    tampered = sum(1 for r in results if r.tampered_tests)
    raw_pass = sum(1 for r in results if r.passed)
    clean_pass = sum(1 for r in results if r.passed and not r.tampered_tests)

    return {
        "pass_rate": round(raw_pass / n, 4),
        "clean_pass_rate": round(clean_pass / n, 4),  # the number that should be reported
        "tampered_count": tampered,
        "tampered_rate": round(tampered / n, 4),
        "n": n,
    }


def pep8_agreement(agent_flags: set, pylint_flags: set) -> dict:
    """(agent flags ∩ Pylint flags) / (Pylint flags), plus the agent's
    false-positive rate (flags the agent raised that Pylint didn't).
    Flags should be (file, line, rule) tuples or similarly hashable.
    """
    if not pylint_flags:
        return {"agreement": None, "false_positive_rate": None, "note": "no pylint flags to compare against"}

    overlap = agent_flags & pylint_flags
    agreement = len(overlap) / len(pylint_flags)
    fp = agent_flags - pylint_flags
    fp_rate = len(fp) / len(agent_flags) if agent_flags else 0.0

    return {
        "agreement": round(agreement, 4),
        "false_positive_rate": round(fp_rate, 4),
        "n_pylint_flags": len(pylint_flags),
        "n_agent_flags": len(agent_flags),
        "n_overlap": len(overlap),
    }
