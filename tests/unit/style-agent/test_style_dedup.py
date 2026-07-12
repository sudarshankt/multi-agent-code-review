# Purpose: Validates deduplication, static triage, and non-.py file paths.
"""Unit tests for StyleAgent dedup logic, _static_triage, and edge cases.

These tests focus on:
- LLM findings that duplicate ruff findings are correctly removed
- Case-insensitive title matching in dedup
- _static_triage returns correct signals for Python code vs non-code
- Non-.py files skip ruff but still run LLM analysis
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.agents.style.agent import StyleAgent
from src.models.finding import Category, Finding, FindingSource, Location, Severity


class FakeLLMService:
    """Minimal FakeLLM for tests in this module."""

    def __init__(self, payload):
        self._payload = payload
        self.complete_calls: list[str] = []

    async def complete(self, prompt, *, system=None):
        self.complete_calls.append(prompt)
        return json.dumps(self._payload)

    async def complete_json(self, prompt, *, system=None):
        from src.services.llm_service import _extract_json
        text = await self.complete(prompt, system=system)
        return _extract_json(text)


# ── Dedup helpers ─────────────────────────────────────────────────────────


def _make_finding(
    title: str,
    source: FindingSource = FindingSource.LLM,
    file_path: str = "test.py",
    start_line: int = 1,
) -> Finding:
    return Finding(
        category=Category.STYLE,
        severity=Severity.LOW,
        title=title,
        description=title,
        location=Location(file_path=file_path, start_line=start_line),
        source=source,
    )


def _ruff_output(items: list[tuple[str, str, int]]) -> list[dict]:
    return [
        {"code": code, "message": msg, "location": {"row": line, "column": 1}}
        for code, msg, line in items
    ]


# ── Dedup Tests ───────────────────────────────────────────────────────────


class TestStyleAgentDedup:
    """Tests for ruff+LLM finding deduplication in analyze()."""

    @pytest.mark.asyncio
    async def test_exact_title_match_is_deduped(self) -> None:
        """An LLM finding with the exact same title as a ruff finding is removed."""
        ruff_raw = _ruff_output([("F401", "`os` imported but unused", 1)])

        # LLM returns a finding whose title matches the ruff title exactly
        llm_payload = [
            {
                "title": "F401: `os` imported but unused",
                "description": "Same as ruff.",
                "severity": "low",
            },
        ]

        code = "import os\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService(llm_payload))

            findings = await agent.analyze(code, "exact.py")

        assert len(findings) == 1
        assert findings[0].source == FindingSource.LINTER

    @pytest.mark.asyncio
    async def test_case_insensitive_dedup(self) -> None:
        """Dedup is case-insensitive on title comparison."""
        ruff_raw = _ruff_output([("W292", "No newline at end of file", 10)])

        llm_payload = [
            {
                "title": "W292: no newline at end of file",
                "description": "case-insensitive dupe of ruff",
                "severity": "low",
            },
        ]

        code = "print('hi')\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService(llm_payload))

            findings = await agent.analyze(code, "case.py")

        assert len(findings) == 1
        assert findings[0].source == FindingSource.LINTER

    @pytest.mark.asyncio
    async def test_partial_title_overlap_not_deduped(self) -> None:
        """LLM finding with only partial title overlap is NOT removed."""
        ruff_raw = _ruff_output([("F401", "`os` imported but unused", 1)])

        llm_payload = [
            {
                "title": "Unused import `os` found in module",
                "description": "Different title format — should survive.",
                "severity": "low",
            },
        ]

        code = "import os\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService(llm_payload))

            findings = await agent.analyze(code, "partial.py")

        assert len(findings) == 2
        sources = {f.source for f in findings}
        assert FindingSource.LINTER in sources
        assert FindingSource.LLM in sources

    @pytest.mark.asyncio
    async def test_dedup_handles_no_ruff_findings(self) -> None:
        """When there are no ruff findings, all LLM findings pass through."""
        llm_payload = [
            {
                "title": "Missing type annotation",
                "description": "Function lacks type hints.",
                "severity": "low",
            },
            {
                "title": "Complex expression",
                "description": "Expression is hard to read.",
                "severity": "low",
            },
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = b"[]"
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService(llm_payload))

            findings = await agent.analyze("def f(x): return x*x\n", "noruff.py")

        assert len(findings) == 2
        assert all(f.source == FindingSource.LLM for f in findings)


# ── Static Triage Tests ───────────────────────────────────────────────────


class TestStyleAgentTriage:
    """Tests for StyleAgent._static_triage()."""

    @pytest.mark.asyncio
    async def test_python_code_with_import_triggers_triage(self) -> None:
        """Code containing 'import ' returns a triage alert."""
        agent = StyleAgent.__new__(StyleAgent)
        result = await agent._static_triage("import os\nprint('hi')\n", "mod.py")

        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0]["type"] == "structure"
        assert "python-structure" in result[0]["token"]

    @pytest.mark.asyncio
    async def test_python_code_with_def_triggers_triage(self) -> None:
        """Code containing 'def ' returns a triage alert."""
        agent = StyleAgent.__new__(StyleAgent)
        result = await agent._static_triage("def foo():\n    pass\n", "func.py")

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_python_code_with_class_triggers_triage(self) -> None:
        """Code containing 'class ' returns a triage alert."""
        agent = StyleAgent.__new__(StyleAgent)
        result = await agent._static_triage("class Foo:\n    pass\n", "cls.py")

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_python_code_with_return_triggers_triage(self) -> None:
        """Code containing 'return' returns a triage alert."""
        agent = StyleAgent.__new__(StyleAgent)
        result = await agent._static_triage("def f():\n    return 1\n", "ret.py")

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_empty_code_returns_empty_triage(self) -> None:
        """Code with no Python structure tokens returns empty list."""
        agent = StyleAgent.__new__(StyleAgent)
        result = await agent._static_triage("bare text, nothing here.", "notes.txt")

        assert result == []

    @pytest.mark.asyncio
    async def test_blank_code_returns_empty_triage(self) -> None:
        """Blank code returns empty list — no structure detected."""
        agent = StyleAgent.__new__(StyleAgent)
        result = await agent._static_triage("\n\n   \n", "blank.py")

        assert result == []

    @pytest.mark.asyncio
    async def test_js_code_returns_empty_triage(self) -> None:
        """JS code without Python keywords returns empty (no 'return' in string)."""
        # 'return' is in the triage check but this is JS code
        agent = StyleAgent.__new__(StyleAgent)
        result = await agent._static_triage(
            "const foo = () => {\n  console.log('hi');\n};\n",
            "app.js",
        )

        assert result == []
