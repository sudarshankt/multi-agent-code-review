"""Bug-detection static analyzers (Python only)."""

from __future__ import annotations

from src.agents.bug_detection.analyzers import runtime, semantic, syntax
from src.models.finding import Finding


def run_all(code: str, file_path: str) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(syntax.analyze(code, file_path))
    # If the file does not parse, semantic/runtime AST passes return nothing.
    findings.extend(semantic.analyze(code, file_path))
    findings.extend(runtime.analyze(code, file_path))
    return findings
