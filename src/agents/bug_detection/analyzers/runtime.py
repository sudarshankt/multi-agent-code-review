"""Runtime-risk analyzer (Python only): patterns that fail at runtime."""

from __future__ import annotations

import ast

from src.agents.ast_utils import attach_parents, parse
from src.models.finding import Category, Confidence, Finding, Location, Severity


def _finding(title: str, desc: str, line: int, file_path: str, suggestion: str,
             severity: Severity = Severity.MEDIUM) -> Finding:
    return Finding(
        category=Category.BUG,
        severity=severity,
        confidence=Confidence.LOW,
        title=title,
        description=desc,
        location=Location(file_path=file_path, start_line=line, end_line=line),
        suggestion=suggestion,
    )


def analyze(code: str, file_path: str) -> list[Finding]:
    tree = parse(code)
    if tree is None:
        return []
    attach_parents(tree)

    findings: list[Finding] = []
    for node in ast.walk(tree):
        # open() not used as a context manager.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            parent = getattr(node, "parent", None)
            if not isinstance(parent, ast.withitem):
                findings.append(
                    _finding(
                        "File opened without context manager",
                        "open() is called outside a 'with' block; the file may not be closed.",
                        node.lineno,
                        file_path,
                        "Use 'with open(...) as f:' to ensure the file is closed.",
                    )
                )
        # assert with a tuple literal is always truthy.
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Tuple):
            findings.append(
                _finding(
                    "Assert on a tuple is always true",
                    "asserting a non-empty tuple literal never fails.",
                    node.lineno,
                    file_path,
                    "Remove the parentheses or assert the intended condition.",
                    severity=Severity.HIGH,
                )
            )
    return findings
