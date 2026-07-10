"""Hotspot analyzer (Python only): expensive patterns inside loops."""

from __future__ import annotations

import ast

from src.agents.ast_utils import attach_parents, is_inside_loop, parse
from src.models.finding import Category, Confidence, Finding, Location, Severity


def _finding(title: str, desc: str, line: int, file_path: str, suggestion: str) -> Finding:
    return Finding(
        category=Category.PERFORMANCE,
        severity=Severity.MEDIUM,
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
        # String concatenation via += inside a loop.
        if (
            isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Add)
            and is_inside_loop(node)
        ):
            findings.append(
                _finding(
                    "String/list build-up with += in loop",
                    "Repeated concatenation inside a loop reallocates each iteration.",
                    node.lineno,
                    file_path,
                    "Accumulate into a list and ''.join() once, or use a buffer.",
                )
            )
        # len()/sorted()/list() recomputed inside loop conditions.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"sorted", "list", "set", "dict"}
            and is_inside_loop(node)
        ):
            findings.append(
                _finding(
                    f"Repeated {node.func.id}() inside loop",
                    f"'{node.func.id}()' is rebuilt on every iteration.",
                    node.lineno,
                    file_path,
                    "Hoist the computation out of the loop if the input is invariant.",
                )
            )
    return findings
