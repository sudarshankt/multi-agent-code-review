#!/usr/bin/env python3
"""LLM-as-judge evaluation of the Fix Agent across configured model candidates.

Findings come from eval/golden/manifest.json (not a live finding-agent run), so
this is independent of the finding agents' own quality. For each model
candidate, FixAgent._fix_file() is called directly per golden case (no git
dependency, no severity/file-count gating from FixAgent.run()), then a judge
LLM scores the resulting fix on correctness/safety/minimality/explanation.

Usage:
    python -m eval.fix_eval.run_eval [--models deepseek,anthropic]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.agents.fix.agent import FixAgent
from src.core.config import Settings, get_settings
from src.core.constants import PYTHON_EXTENSIONS
from src.core.logging import configure_logging, get_logger
from src.models.finding import Category, Confidence, Finding, Location, Severity
from src.prompts.loader import render
from src.services.llm_service import LLMService

from eval.fix_eval.models import FixCaseResult, FixEvalReport, JudgeScore, ModelCandidate
from eval.fix_eval.scoring import aggregate_model_metrics
from eval.golden.models import GoldenCase

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "eval" / "golden" / "manifest.json"
CANDIDATES_PATH = REPO_ROOT / "eval" / "fix_eval" / "model_candidates.json"
RESULTS_DIR = REPO_ROOT / "eval" / "results" / "fix"

_SEVERITY_ALIASES = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "moderate": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
    "informational": Severity.INFO,
}

GoldenFindingCase = tuple[str, str, list[Finding]]  # (category, file_path, findings)


def _coerce_severity(value: str | None) -> Severity:
    if not value:
        return Severity.MEDIUM
    return _SEVERITY_ALIASES.get(value.strip().lower(), Severity.MEDIUM)


def load_golden_findings() -> list[GoldenFindingCase]:
    """Build (category, file_path, findings) tuples from the golden manifest."""
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    cases: list[GoldenFindingCase] = []
    for category_name, raw_cases in raw.items():
        for raw_case in raw_cases:
            case = GoldenCase.model_validate(raw_case)
            if not case.expected:
                continue
            findings = [
                Finding(
                    category=Category(category_name),
                    severity=_coerce_severity(exp.severity),
                    confidence=Confidence.MEDIUM,
                    title=exp.description[:200],
                    description=exp.description,
                    location=Location(
                        file_path=case.file, start_line=exp.start_line, end_line=exp.end_line
                    ),
                )
                for exp in case.expected
            ]
            cases.append((category_name, case.file, findings))
    return cases


def load_model_candidates() -> list[ModelCandidate]:
    with open(CANDIDATES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return [ModelCandidate.model_validate(item) for item in raw]


def build_llm_for_candidate(candidate: ModelCandidate) -> LLMService:
    settings = Settings(model_provider=candidate.model_provider, primary_model=candidate.primary_model)
    return LLMService(settings)


def build_judge_llm() -> LLMService:
    base = get_settings()
    provider = base.judge_model_provider or base.model_provider
    model = base.judge_primary_model or base.primary_model
    settings = Settings(model_provider=provider, primary_model=model)
    return LLMService(settings)


def _validate_syntax(code: str) -> bool:
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


async def judge_fix(
    judge_llm: LLMService,
    category: str,
    file_path: str,
    findings: list[Finding],
    original_code: str,
    fixed_code: str,
    explanation: str,
) -> JudgeScore | None:
    prompt = render(
        "fix_judge.j2",
        category=category,
        file_path=file_path,
        findings=findings,
        original_code=original_code,
        fixed_code=fixed_code,
        explanation=explanation,
    )
    try:
        payload = await judge_llm.complete_json(prompt)
    except Exception as exc:  # noqa: BLE001 - one bad judge call must not halt the run
        logger.warning("judge_call_failed", file=file_path, error=str(exc))
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return JudgeScore.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - malformed judge response
        logger.warning("judge_response_invalid", file=file_path, error=str(exc))
        return None


async def run_candidate(
    candidate: ModelCandidate,
    cases: list[GoldenFindingCase],
    files: dict[str, str],
    judge_llm: LLMService,
) -> list[FixCaseResult]:
    fix_agent = FixAgent(llm=build_llm_for_candidate(candidate))
    results: list[FixCaseResult] = []

    for category, file_path, findings in cases:
        code = files[file_path]
        fix_result, fixed_code = await fix_agent._fix_file(code, file_path, findings, category)

        syntax_valid = None
        judge_score = None
        if fix_result.success and fixed_code:
            if file_path.endswith(PYTHON_EXTENSIONS):
                syntax_valid = _validate_syntax(fixed_code)
            judge_score = await judge_fix(
                judge_llm, category, file_path, findings, code, fixed_code,
                fix_result.explanation or "",
            )

        results.append(
            FixCaseResult(
                model_label=candidate.label,
                file=file_path,
                category=category,
                success=fix_result.success,
                syntax_valid=syntax_valid,
                error=fix_result.error,
                judge=judge_score,
            )
        )
    return results


async def run_all(model_filter: set[str] | None) -> FixEvalReport:
    cases = load_golden_findings()
    files = {
        file_path: (REPO_ROOT / file_path).read_text(encoding="utf-8")
        for _, file_path, _ in cases
    }
    candidates = load_model_candidates()
    judge_llm = build_judge_llm()

    report = FixEvalReport()
    for candidate in candidates:
        if model_filter and candidate.label not in model_filter:
            continue
        logger.info("fix_eval_model_start", model=candidate.label, cases=len(cases))
        case_results = await run_candidate(candidate, cases, files, judge_llm)
        metrics = aggregate_model_metrics(candidate.label, case_results)
        report.models.append(metrics)
        logger.info(
            "fix_eval_model_complete",
            model=candidate.label,
            success_rate=metrics.success_rate,
            resolved_rate=metrics.resolved_rate,
            avg_correctness=metrics.avg_correctness,
        )
    return report


def print_matrix(report: FixEvalReport) -> None:
    header = (
        f"{'model':<12} {'cases':>5} {'success':>8} {'syntax':>7} {'resolved':>9} "
        f"{'correct':>8} {'safety':>7} {'minimal':>8} {'explain':>8}"
    )
    print(header)
    print("-" * len(header))
    for m in report.models:
        print(
            f"{m.model_label:<12} {m.cases:>5} {m.success_rate:>8.3f} {m.syntax_valid_rate:>7.3f} "
            f"{m.resolved_rate:>9.3f} {m.avg_correctness:>8.3f} {m.avg_safety:>7.3f} "
            f"{m.avg_minimality:>8.3f} {m.avg_explanation_quality:>8.3f}"
        )


def save_report(report: FixEvalReport) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(RESULTS_DIR.glob("run-*.json"))
    next_id = len(existing) + 1
    out_path = RESULTS_DIR / f"run-{next_id:04d}.json"
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    latest_path = RESULTS_DIR / "latest.json"
    latest_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", help="Comma-separated subset of candidate labels to run", default=None
    )
    args = parser.parse_args()

    configure_logging()

    model_filter = set(args.models.split(",")) if args.models else None
    report = asyncio.run(run_all(model_filter))

    print_matrix(report)
    out_path = save_report(report)
    print(f"\nSaved report to {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
