"""Syntax-level analyzer (Python only)."""

from __future__ import annotations

import ast

from src.models.finding import Category, Confidence, Finding, Location, Severity


def analyze(code: str, file_path: str) -> list[Finding]:
    try:
        ast.parse(code)
        return []
    except SyntaxError as exc:
        return [
            Finding(
                category=Category.BUG,
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                title="Syntax error",
                description=f"File does not parse: {exc.msg}",
                location=Location(
                    file_path=file_path,
                    start_line=exc.lineno,
                    end_line=exc.lineno,
                    snippet=exc.text.strip() if exc.text else None,
                ),
                suggestion="Fix the syntax error so the file can be parsed.",
            )
        ]
