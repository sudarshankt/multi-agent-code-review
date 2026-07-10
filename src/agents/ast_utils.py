"""Shared helpers for Python AST-based analyzers."""

from __future__ import annotations

import ast


def parse(code: str) -> ast.Module | None:
    """Parse Python source, returning None on syntax error."""
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


def attach_parents(tree: ast.AST) -> None:
    """Annotate each node with a `parent` attribute."""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]


def loop_depth(node: ast.AST) -> int:
    """Number of enclosing loops for a node (requires attach_parents)."""
    depth = 0
    current = getattr(node, "parent", None)
    while current is not None:
        if isinstance(current, (ast.For, ast.While, ast.AsyncFor)):
            depth += 1
        current = getattr(current, "parent", None)
    return depth


def is_inside_loop(node: ast.AST) -> bool:
    return loop_depth(node) > 0
