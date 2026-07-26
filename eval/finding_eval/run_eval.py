#!/usr/bin/env python3
"""Run the finding-agent evaluation matrix against eval/golden/manifest.json.

Usage:
    python -m eval.finding_eval.run_eval [--agent security,bug_detection]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.agents.base import BaseAnalysisAgent
from src.agents.bug_detection.agent import BugDetectionAgent
from src.agents.performance.agent import PerformanceAgent
from src.agents.security.agent import SecurityAgent
from src.agents.style.agent import StyleAgent
from src.core.constants import AGENT_BUG, AGENT_PERFORMANCE, AGENT_SECURITY, AGENT_STYLE
from src.core.logging import configure_logging, get_logger

from eval.finding_eval.models import EvalReport
from eval.finding_eval.scoring import aggregate_metrics, match_case
from eval.golden.models import ExpectedFinding, GoldenCase

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "eval" / "golden" / "manifest.json"
RESULTS_DIR = REPO_ROOT / "eval" / "results" / "finding"

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


async def run_agent_eval(agent_name: str, cases: list[GoldenCase]) -> list:
    agent = AGENT_FACTORIES[agent_name]()

    files: dict[str, str] = {}
    expected_by_file: dict[str, list[ExpectedFinding]] = {}
    for case in cases:
        abs_path = REPO_ROOT / case.file
        files[case.file] = abs_path.read_text(encoding="utf-8")
        expected_by_file[case.file] = case.expected

    findings = await agent.run(files, {"triage_enabled": True})

    findings_by_file: dict[str, list] = {file_path: [] for file_path in files}
    for finding in findings:
        findings_by_file.setdefault(finding.location.file_path, []).append(finding)

    return [
        match_case(file_path, expected_by_file[file_path], findings_by_file.get(file_path, []))
        for file_path in files
    ]


async def run_all(agent_filter: set[str] | None) -> EvalReport:
    manifest = load_manifest()
    report = EvalReport()

    for agent_name, cases in manifest.items():
        if agent_filter and agent_name not in agent_filter:
            continue
        if not cases:
            continue
        logger.info("eval_agent_start", agent_name=agent_name, cases=len(cases))
        case_results = await run_agent_eval(agent_name, cases)
        metrics = aggregate_metrics(agent_name, case_results)
        report.agents.append(metrics)
        logger.info(
            "eval_agent_complete",
            agent_name=agent_name,
            precision=metrics.precision,
            recall=metrics.recall,
            f1=metrics.f1,
        )

    return report


def print_matrix(report: EvalReport) -> None:
    header = (
        f"{'agent':<16} {'TP':>4} {'FP':>4} {'FN':>4} {'precision':>10} {'recall':>8} "
        f"{'f1':>6} {'similarity':>10}"
    )
    print(header)
    print("-" * len(header))
    for m in report.agents:
        print(
            f"{m.agent_name:<16} {m.true_positives:>4} {m.false_positives:>4} {m.false_negatives:>4} "
            f"{m.precision:>10.3f} {m.recall:>8.3f} {m.f1:>6.3f} {m.avg_similarity:>10.3f}"
        )


def save_report(report: EvalReport) -> Path:
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
