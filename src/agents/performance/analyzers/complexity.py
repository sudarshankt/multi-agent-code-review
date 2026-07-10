"""Complexity analyzer (Python only): nested loops and long functions."""

from __future__ import annotations

import ast

from src.agents.ast_utils import attach_parents, loop_depth, parse
from src.models.finding import Category, Confidence, Finding, Location, Severity

LONG_FUNCTION_LINES = 80


def analyze(code: str, file_path: str) -> list[Finding]:
    tree = parse(code)
    if tree is None:
        return []
    attach_parents(tree)

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
            depth = loop_depth(node) + 1
            if depth >= 2:
                findings.append(
                    Finding(
                        category=Category.PERFORMANCE,
                        severity=Severity.MEDIUM if depth == 2 else Severity.HIGH,
                        confidence=Confidence.MEDIUM,
                        title=f"Nested loops (depth {depth})",
                        description="Nested loops can lead to quadratic or worse time complexity.",
                        location=Location(file_path=file_path, start_line=node.lineno, end_line=node.lineno),
                        suggestion="Consider restructuring with a hash map or vectorized operation.",
                    )
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            length = end - node.lineno
            if length > LONG_FUNCTION_LINES:
                findings.append(
                    Finding(
                        category=Category.PERFORMANCE,
                        severity=Severity.LOW,
                        confidence=Confidence.LOW,
                        title=f"Long function '{node.name}' ({length} lines)",
                        description="Very long functions are harder to optimize and reason about.",
                        location=Location(file_path=file_path, start_line=node.lineno, end_line=end),
                        suggestion="Break the function into smaller units.",
                    )
                )
    return findings
