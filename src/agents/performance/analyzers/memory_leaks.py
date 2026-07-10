"""Memory-leak analyzer (Python only).

Heuristic: an unbounded container (list/dict/set) that is appended to / inserted
inside a loop, where the container is defined outside that loop (module/class
scope or an enclosing function), suggesting unbounded growth.

NOTE (Build_from_Scratch.md bug #10): severity selection uses explicit if/elif,
NOT a chained `X and Y and Z if COND else W` ternary, whose operator precedence
is surprising and was the source of a real bug.
"""

from __future__ import annotations

import ast

from src.agents.ast_utils import attach_parents, is_inside_loop, parse
from src.models.finding import Category, Confidence, Finding, Location, Severity

_GROWTH_METHODS = {"append", "extend", "add", "update", "insert"}


def _select_severity(in_loop: bool, is_global: bool, unbounded: bool) -> Severity:
    # Explicit branching on purpose (bug #10) — do NOT collapse into a ternary.
    if in_loop and is_global and unbounded:
        severity = Severity.HIGH
    elif in_loop and unbounded:
        severity = Severity.MEDIUM
    elif in_loop:
        severity = Severity.LOW
    else:
        severity = Severity.INFO
    return severity


def _module_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def analyze(code: str, file_path: str) -> list[Finding]:
    tree = parse(code)
    if tree is None:
        return []
    attach_parents(tree)
    global_names = _module_level_names(tree)

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _GROWTH_METHODS:
            continue
        target = func.value
        if not isinstance(target, ast.Name):
            continue

        in_loop = is_inside_loop(node)
        if not in_loop:
            continue

        is_global = target.id in global_names
        # We cannot prove a bound statically; treat loop growth as potentially unbounded.
        unbounded = True
        severity = _select_severity(in_loop, is_global, unbounded)

        findings.append(
            Finding(
                category=Category.PERFORMANCE,
                severity=severity,
                confidence=Confidence.LOW,
                title=f"Potential unbounded growth of '{target.id}'",
                description=(
                    f"'{target.id}.{func.attr}()' is called inside a loop"
                    + (" and the container is module-level" if is_global else "")
                    + "; this can grow without bound."
                ),
                location=Location(file_path=file_path, start_line=node.lineno, end_line=node.lineno),
                suggestion="Bound the container size, clear it periodically, or stream results.",
            )
        )
    return findings
