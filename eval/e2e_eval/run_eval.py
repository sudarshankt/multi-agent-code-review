#!/usr/bin/env python3
"""End-to-end evaluation of the finding-agent -> fix-agent pipeline.

Unlike finding_eval (finding agents only, scored against golden findings) and
fix_eval (fix agent only, fed golden-derived findings and bypassing the
finding agents entirely), this eval chains the two live: it runs each finding
agent, matches its output against eval/golden/manifest.json, and then runs
the fix agent only on the findings that were actually matched -- exactly what
happens in production, where the fix agent only ever sees what the finding
agent surfaced.

This is the only eval that can catch compounding failures across the
finder/fixer handoff (e.g. a slightly-off line range or vague description
that the fix agent then mishandles), since fix_eval always feeds the fix
agent clean, golden-derived findings. It intentionally does NOT replace
finding_eval or fix_eval: keep using those to isolate which stage regressed.

Usage:
    python -m eval.e2e_eval.run_eval [--agent security,bug_detection]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.agents.base import BaseAnalysisAgent
from src.agents.bug_detection.agent import BugDetectionAgent
from src.agents.fix.agent import FixAgent
from src.agents.performance.agent import PerformanceAgent
from src.agents.security.agent import SecurityAgent
from src.agents.style.agent import StyleAgent
from src.core.config import Settings, get_settings
from src.core.constants import (
    AGENT_BUG,
    AGENT_PERFORMANCE,
    AGENT_SECURITY,
    AGENT_STYLE,
    PYTHON_EXTENSIONS,
)
from src.core.logging import configure_logging, get_logger
from src.models.finding import Finding
from src.services.llm_service import LLMService

from eval.e2e_eval.models import E2EReport, PipelineCaseResult
from eval.e2e_eval.scoring import aggregate_pipeline_metrics, match_and_fix_inputs
from eval.fix_eval.run_eval import judge_fix
from eval.golden.models import ExpectedFinding, GoldenCase

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "eval" / "golden" / "manifest.json"
RESULTS_DIR = REPO_ROOT / "eval" / "results" / "e2e"

AGENT_FACTORIES: dict[str, type[BaseAnalysisAgent]] = {
    AGENT_SECURITY: SecurityAgent,
    AGENT_BUG: BugDetectionAgent,
    AGENT_STYLE: StyleAgent,
    AGENT_PERFORMANCE: PerformanceAgent,
}


def load_manifest() -> dict[str, list[GoldenCase]]:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return {
        agent_name: [GoldenCase.model_validate(case) for case in cases]
        for agent_name, cases in raw.items()
    }


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


async def run_agent_pipeline(
    agent_name: str,
    cases: list[GoldenCase],
    fix_agent: FixAgent,
    judge_llm: LLMService,
) -> list[PipelineCaseResult]:
    agent = AGENT_FACTORIES[agent_name]()

    files: dict[str, str] = {}
    expected_by_file: dict[str, list[ExpectedFinding]] = {}
    for case in cases:
        abs_path = REPO_ROOT / case.file
        files[case.file] = abs_path.read_text(encoding="utf-8")
        expected_by_file[case.file] = case.expected

    findings = await agent.run(files, {"triage_enabled": True})

    findings_by_file: dict[str, list[Finding]] = {file_path: [] for file_path in files}
    for finding in findings:
        findings_by_file.setdefault(finding.location.file_path, []).append(finding)

    results: list[PipelineCaseResult] = []
    for file_path in files:
        code = files[file_path]
        case_result, matched_findings = match_and_fix_inputs(
            file_path, expected_by_file[file_path], findings_by_file.get(file_path, [])
        )

        if not matched_findings:
            results.append(PipelineCaseResult(finding=case_result))
            continue

        fix_result, fixed_code = await fix_agent._fix_file(
            code, file_path, matched_findings, agent_name
        )

        syntax_valid = None
        judge_score = None
        if fix_result.success and fixed_code:
            if file_path.endswith(PYTHON_EXTENSIONS):
                syntax_valid = _validate_syntax(fixed_code)
            judge_score = await judge_fix(
                judge_llm, agent_name, file_path, matched_findings, code, fixed_code,
                fix_result.explanation or "",
            )

        results.append(
            PipelineCaseResult(
                finding=case_result,
                fix_attempted=True,
                fix_success=fix_result.success,
                syntax_valid=syntax_valid,
                fix_error=fix_result.error,
                judge=judge_score,
            )
        )
    return results


async def run_all(agent_filter: set[str] | None) -> E2EReport:
    manifest = load_manifest()
    fix_agent = FixAgent()
    judge_llm = build_judge_llm()

    report = E2EReport()
    for agent_name, cases in manifest.items():
        if agent_filter and agent_name not in agent_filter:
            continue
        if not cases:
            continue
        logger.info("e2e_eval_agent_start", agent_name=agent_name, cases=len(cases))
        case_results = await run_agent_pipeline(agent_name, cases, fix_agent, judge_llm)
        metrics = aggregate_pipeline_metrics(agent_name, case_results)
        report.agents.append(metrics)
        logger.info(
            "e2e_eval_agent_complete",
            agent_name=agent_name,
            precision=metrics.precision,
            recall=metrics.recall,
            resolved_rate=metrics.resolved_rate,
        )

    return report


def print_matrix(report: E2EReport) -> None:
    header = (
        f"{'agent':<16} {'TP':>4} {'FP':>4} {'FN':>4} {'precision':>10} {'recall':>8} "
        f"{'f1':>6} {'fix_ok':>7} {'resolved':>9}"
    )
    print(header)
    print("-" * len(header))
    for m in report.agents:
        print(
            f"{m.agent_name:<16} {m.true_positives:>4} {m.false_positives:>4} {m.false_negatives:>4} "
            f"{m.precision:>10.3f} {m.recall:>8.3f} {m.f1:>6.3f} {m.fix_success_rate:>7.3f} "
            f"{m.resolved_rate:>9.3f}"
        )


def save_report(report: E2EReport) -> Path:
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
        "--agent",
        help="Comma-separated subset of agents to run (default: all)",
        default=None,
    )
    args = parser.parse_args()

    configure_logging()

    agent_filter = set(args.agent.split(",")) if args.agent else None
    report = asyncio.run(run_all(agent_filter))

    print_matrix(report)
    out_path = save_report(report)
    print(f"\nSaved report to {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
