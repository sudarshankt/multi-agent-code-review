"""Performance static analyzers (Python only)."""

from __future__ import annotations

from src.agents.performance.analyzers import complexity, hotspots, memory_leaks
from src.models.finding import Finding


def run_all(code: str, file_path: str) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(complexity.analyze(code, file_path))
    findings.extend(memory_leaks.analyze(code, file_path))
    findings.extend(hotspots.analyze(code, file_path))
    return findings
