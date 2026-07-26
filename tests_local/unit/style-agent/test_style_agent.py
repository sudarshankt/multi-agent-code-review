# Purpose: Validates StyleAgent.analyze() end-to-end with fake LLM + mocked ruff.
"""Unit tests for StyleAgent.analyze() — full pipeline with FakeLLM and golden files.

These tests validate the complete StyleAgent.analyze() flow:
  ruff lint → prompt rendering → LLM call → JSON parsing → dedup → Finding objects

The LLM is replaced with a FakeLLMService and ruff is mocked, so these tests
are deterministic and require no API keys, network access, or ruff binary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.agents.style.agent import StyleAgent
from src.models.finding import Category, FindingSource

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_fixture_json(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text())


# ── Fake LLM Service ──────────────────────────────────────────────────────


class FakeLLMService:
    """A test double for LLMService that returns canned JSON responses."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.complete_calls: list[str] = []

    async def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        self.complete_calls.append(prompt)
        return json.dumps(self._payload)

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        from src.services.llm_service import _extract_json

        text = await self.complete(prompt, system=system)
        return _extract_json(text)


# ── Mock ruff result builder ──────────────────────────────────────────────


def _make_ruff_output(items: list[tuple[str, str, int]]) -> list[dict[str, Any]]:
    """Build ruff JSON output from (code, message, line) tuples."""
    return [
        {"code": code, "message": msg, "location": {"row": line, "column": 1}}
        for code, msg, line in items
    ]


# ── Tests ─────────────────────────────────────────────────────────────────


class TestStyleAgentAnalyze:
    """Full-pipeline tests for StyleAgent.analyze() with mocked ruff."""

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _make_agent(
        llm_payload: Any | None = None,
        *,
        ruff_output: list[dict[str, Any]] | None = None,
    ) -> StyleAgent:
        """Create a StyleAgent with FakeLLM and mocked ruff."""
        if llm_payload is None:
            llm_payload = []

        fake_llm = FakeLLMService(llm_payload)
        ruff_data = ruff_output or []
        ruff_json = json.dumps(ruff_data).encode()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ruff_json
            mock_run.return_value.stderr = b""

            agent = StyleAgent(llm=fake_llm)

        return agent

    # ── basic flow ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_analyze_with_ruff_and_llm_findings(self) -> None:
        """Both ruff and LLM findings are returned, LLM dupes are filtered."""
        ruff_raw = _make_ruff_output([
            ("W292", "No newline at end of file", 10),
            ("F401", "`os` imported but unused", 1),
        ])

        llm_payload = [
            {
                "title": "Unused variable in loop",
                "description": "The variable `idx` is assigned but never read.",
                "severity": "low",
                "start_line": 15,
            },
            {
                "title": "W292: no newline at end of file",
                "description": "A ruff duplicate — should be deduped.",
                "severity": "low",
                "start_line": 10,
            },
        ]

        code = "import os\n\ndef foo():\n    pass\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService(llm_payload))

            findings = await agent.analyze(code, "test.py")

        # 2 ruff + 1 LLM (1 was deduped)
        assert len(findings) == 3

        ruff = [f for f in findings if f.source == FindingSource.LINTER]
        llm = [f for f in findings if f.source == FindingSource.LLM]

        assert len(ruff) == 2
        assert len(llm) == 1
        assert llm[0].title == "Unused variable in loop"

    @pytest.mark.asyncio
    async def test_analyze_ruff_only_no_llm_findings(self) -> None:
        """When LLM returns empty list, only ruff findings are included."""
        ruff_raw = _make_ruff_output([
            ("E501", "Line too long (120 > 100)", 5),
        ])

        code = "print('hello' * 200)\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService([]))

            findings = await agent.analyze(code, "app.py")

        assert len(findings) == 1
        assert findings[0].source == FindingSource.LINTER
        assert "E501" in findings[0].title

    @pytest.mark.asyncio
    async def test_analyze_llm_only_ruff_empty(self) -> None:
        """When ruff returns no issues, LLM findings are still included."""
        llm_payload = [
            {
                "title": "Missing docstring",
                "description": "Function `bar` has no docstring.",
                "severity": "low",
                "start_line": 3,
            },
        ]

        code = "def bar():\n    return 42\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = b"[]"
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService(llm_payload))

            findings = await agent.analyze(code, "util.py")

        assert len(findings) == 1
        assert findings[0].title == "Missing docstring"
        assert findings[0].source == FindingSource.LLM

    @pytest.mark.asyncio
    async def test_analyze_no_findings(self) -> None:
        """Clean code with no ruff issues and empty LLM response → no findings."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = b"[]"
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService([]))

            findings = await agent.analyze("print('ok')\n", "clean.py")

        assert findings == []

    @pytest.mark.asyncio
    async def test_analyze_non_python_file_skips_ruff(self) -> None:
        """Non-.py files skip ruff entirely but still go through LLM."""
        llm_payload = [
            {
                "title": "Unclear variable naming",
                "description": "Variable `a` is poorly named.",
                "severity": "low",
            },
        ]

        agent = StyleAgent(llm=FakeLLMService(llm_payload))
        findings = await agent.analyze("var a = 1;\n", "script.js")

        assert len(findings) == 1
        assert findings[0].category == Category.STYLE
        # No ruff findings for .js files
        ruff = [f for f in findings if f.source == FindingSource.LINTER]
        assert len(ruff) == 0

    @pytest.mark.asyncio
    async def test_analyze_all_llm_findings_are_ruff_dupes(self) -> None:
        """When every LLM finding duplicates a ruff finding, all are deduped."""
        ruff_raw = _make_ruff_output([
            ("F401", "`os` imported but unused", 1),
            ("W293", "Blank line contains whitespace", 3),
        ])

        llm_payload = [
            {
                "title": "F401: `os` imported but unused",
                "description": "ruff dupe 1",
                "severity": "low",
            },
            {
                "title": "W293: blank line contains whitespace",
                "description": "ruff dupe 2",
                "severity": "low",
            },
        ]

        code = "import os\n\n   \ndef f(): pass\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService(llm_payload))

            findings = await agent.analyze(code, "dup.py")

        assert len(findings) == 2
        assert all(f.source == FindingSource.LINTER for f in findings)

    # ── findings metadata ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_findings_have_correct_category(self) -> None:
        """All findings from StyleAgent have Category.STYLE."""
        ruff_raw = _make_ruff_output([("F401", "`sys` imported but unused", 1)])

        code = "import sys\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService([]))

            findings = await agent.analyze(code, "mod.py")

        assert all(f.category == Category.STYLE for f in findings)

    @pytest.mark.asyncio
    async def test_findings_have_agent_name_set(self) -> None:
        """StyleAgent stamps 'style' on all returned findings via run()."""
        ruff_raw = _make_ruff_output([("F401", "unused import", 1)])

        code = "import json\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService([]))

            findings = await agent.run({"a.py": code})

        assert all(f.agent_name == "style" for f in findings)

    @pytest.mark.asyncio
    async def test_findings_have_correct_file_path(self) -> None:
        """All findings reference the analyzed file path."""
        llm_payload = [
            {
                "title": "Dead code",
                "description": "Unreachable code after return.",
                "severity": "low",
                "start_line": 4,
            },
        ]

        code = "def f():\n    return 1\n    x = 2\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = b"[]"
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService(llm_payload))

            findings = await agent.analyze(code, "lib/helpers.py")

        assert all(f.location.file_path == "lib/helpers.py" for f in findings)

    @pytest.mark.asyncio
    async def test_ruff_findings_have_linter_source(self) -> None:
        """Ruff-originated findings carry source=FindingSource.LINTER."""
        ruff_raw = _make_ruff_output([("F401", "unused", 1)])

        code = "import os\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=FakeLLMService([]))

            findings = await agent.analyze(code, "f.py")

        ruff = [f for f in findings if f.source == FindingSource.LINTER]
        assert len(ruff) == 1
        assert ruff[0].source == FindingSource.LINTER

    # ── ruff unavailable path ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_analyze_when_ruff_binary_missing(self) -> None:
        """When ruff is not installed, LLM findings are still produced."""
        llm_payload = [
            {
                "title": "Complex function",
                "description": "Function is too long.",
                "severity": "low",
            },
        ]

        with patch("subprocess.run", side_effect=FileNotFoundError):
            agent = StyleAgent(llm=FakeLLMService(llm_payload))
            findings = await agent.analyze("def f(): pass\n", "mod.py")

        assert len(findings) == 1
        assert findings[0].source == FindingSource.LLM
        assert findings[0].title == "Complex function"

    @pytest.mark.asyncio
    async def test_analyze_when_ruff_times_out(self) -> None:
        """When ruff times out, LLM findings are still produced."""
        import subprocess

        llm_payload = [
            {"title": "Naming issue", "description": "Bad name.", "severity": "low"},
        ]

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruff", 10)):
            agent = StyleAgent(llm=FakeLLMService(llm_payload))
            findings = await agent.analyze("x = 1\n", "slow.py")

        assert len(findings) == 1
        assert findings[0].title == "Naming issue"

    # ── edge cases ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_analyze_handles_malformed_llm_output(self) -> None:
        """When the LLM returns non-JSON, only ruff findings survive."""
        ruff_raw = _make_ruff_output([("W292", "No newline at end of file", 3)])

        fake_llm = FakeLLMService("this is not json at all")
        code = "x = 1\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            agent = StyleAgent(llm=fake_llm)

            findings = await agent.analyze(code, "bad.py")

        assert len(findings) == 1
        assert findings[0].source == FindingSource.LINTER

    @pytest.mark.asyncio
    async def test_analyze_with_diff_context(self) -> None:
        """Diff context is passed through to the LLM prompt."""
        llm_payload = [
            {"title": "Style issue", "description": "desc", "severity": "low"},
        ]

        diff = "@@ -1,3 +1,4 @@\n def foo():\n-    pass\n+    return 1\n"
        context = {"diffs": {"src/main.py": diff}}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = b"[]"
            mock_run.return_value.stderr = b""
            fake_llm = FakeLLMService(llm_payload)
            agent = StyleAgent(llm=fake_llm)

            await agent.analyze("def foo():\n    return 1\n", "src/main.py", context)

        # The prompt should contain the diff content
        prompt = fake_llm.complete_calls[0]
        assert "def foo()" in prompt
        assert "return 1" in prompt

    @pytest.mark.asyncio
    async def test_analyze_prompt_includes_ruff_hints(self) -> None:
        """The LLM prompt includes ruff issues as hints to avoid duplication."""
        ruff_raw = _make_ruff_output([("F401", "`os` imported but unused", 1)])

        code = "import os\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""
            fake_llm = FakeLLMService([])
            agent = StyleAgent(llm=fake_llm)

            await agent.analyze(code, "hints.py")

        prompt = fake_llm.complete_calls[0]
        assert "F401" in prompt
        assert "os" in prompt.lower() or "import" in prompt.lower()
