"""Semantic bug analyzer (Python only): high-signal anti-patterns."""

from __future__ import annotations

import ast

from src.agents.ast_utils import parse
from src.models.finding import Category, Confidence, Finding, Location, Severity


def _finding(title: str, desc: str, line: int, file_path: str, suggestion: str,
             severity: Severity = Severity.MEDIUM) -> Finding:
    return Finding(
        category=Category.BUG,
        severity=severity,
        confidence=Confidence.MEDIUM,
        title=title,
        description=desc,
        location=Location(file_path=file_path, start_line=line, end_line=line),
        suggestion=suggestion,
    )


def analyze(code: str, file_path: str) -> list[Finding]:
    tree = parse(code)
    if tree is None:
        return []

    findings: list[Finding] = []
    for node in ast.walk(tree):
        # Mutable default argument.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(
                        _finding(
                            "Mutable default argument",
                            f"Function '{node.name}' uses a mutable default argument, "
                            "which is shared across calls.",
                            node.lineno,
                            file_path,
                            "Use None as the default and create the container inside the function.",
                        )
                    )
        # Comparison to None with == / !=.
        if isinstance(node, ast.Compare):
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and (
                    isinstance(comparator, ast.Constant) and comparator.value is None
                ):
                    findings.append(
                        _finding(
                            "Comparison to None with ==",
                            "Use 'is'/'is not' when comparing to None.",
                            node.lineno,
                            file_path,
                            "Replace '== None' with 'is None'.",
                            severity=Severity.LOW,
                        )
                    )
        # Bare or overly broad except that swallows errors.
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append(
                    _finding(
                        "Bare except",
                        "A bare 'except:' catches everything including KeyboardInterrupt.",
                        node.lineno,
                        file_path,
                        "Catch a specific exception type.",
                        severity=Severity.HIGH,
                    )
                )
            if all(isinstance(stmt, ast.Pass) for stmt in node.body):
                findings.append(
                    _finding(
                        "Silently swallowed exception",
                        "Exception handler body is just 'pass', hiding failures.",
                        node.lineno,
                        file_path,
                        "Log or handle the exception rather than ignoring it.",
                    )
                )
    return findings
