"""Unit tests for SecurityAgent — full pipeline with fake LLM and golden files.

These tests validate the complete SecurityAgent.analyze() flow:
  retriever → prompt rendering → LLM call → JSON parsing → Finding objects

The LLM is replaced with a FakeLLMService that returns canned responses, so these
tests are deterministic and require no API keys or network access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.parsing import findings_from_llm
from src.agents.security.agent import SecurityAgent
from src.agents.security.retriever import SecurityRetriever
from src.core.constants import AGENT_SECURITY, MAX_CODE_CHARS_FOR_RAG
from src.models.finding import Category, Confidence, Finding, Severity

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture_json(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text())


# ── Fake LLM Service ──────────────────────────────────────────────────────


class FakeLLMService:
    """A test double for LLMService that returns canned JSON responses.

    Pass the desired payload (list or dict) and it will be serialised as the
    raw LLM text response.  `complete_json` will then parse it through
    `_extract_json` just like the real path.
    """

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.complete_calls: list[str] = []

    async def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        self.complete_calls.append(prompt)
        return json.dumps(self._payload)

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        # Replicate the real path: complete → _extract_json
        from src.services.llm_service import _extract_json

        text = await self.complete(prompt, system=system)
        return _extract_json(text)


# ── Tests ─────────────────────────────────────────────────────────────────


class TestSecurityAgent:
    """Full-pipeline tests for SecurityAgent.analyze()."""

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _make_agent(
        llm_payload: Any | None = None,
        *,
        chroma_docs: list[str] | None = None,
    ) -> SecurityAgent:
        """Create a SecurityAgent with a FakeLLMService and optionally mocked retriever."""
        if llm_payload is None:
            llm_payload = _load_fixture_json("security_llm_response.json")

        fake_llm = FakeLLMService(llm_payload)
        retriever = SecurityRetriever(top_k=5)

        if chroma_docs is not None:
            # Patch ChromaDB so we control the RAG context precisely
            retriever = SecurityRetriever(top_k=len(chroma_docs))

        agent = SecurityAgent(llm=fake_llm, retriever=retriever)

        if chroma_docs is not None:
            # Return specific docs from _query_chromadb
            agent.retriever._query_chromadb = lambda _q: chroma_docs

        return agent

    # ── basic flow ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_analyze_returns_correct_number_of_findings(self) -> None:
        """A valid LLM response produces the expected number of Finding objects."""
        agent = self._make_agent(
            chroma_docs=["CWE-89: SQL injection guidance."],
        )
        code = (FIXTURES_DIR / "vulnerable_sample.py").read_text()

        findings = await agent.analyze(code, "src/auth.py")

        assert len(findings) == 3

    @pytest.mark.asyncio
    async def test_analyze_empty_response(self) -> None:
        """An empty LLM response produces no findings (clean code path)."""
        agent = self._make_agent(llm_payload=[],
                                 chroma_docs=["CWE-89 fallback"])
        code = "print('hello world')"

        findings = await agent.analyze(code, "clean.py")

        assert findings == []

    @pytest.mark.asyncio
    async def test_analyze_handles_malformed_llm_output(self) -> None:
        """When the LLM returns non-JSON text, findings are empty (graceful)."""
        fake_llm = FakeLLMService("this is not json at all, just prose")
        retriever = SecurityRetriever(top_k=3)
        retriever._query_chromadb = lambda _q: []
        agent = SecurityAgent(llm=fake_llm, retriever=retriever)

        findings = await agent.analyze("some code", "file.py")

        assert findings == []

    # ── findings metadata ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_findings_have_correct_category(self) -> None:
        """All findings from SecurityAgent have Category.SECURITY."""
        agent = self._make_agent(chroma_docs=["CWE-89"])
        code = (FIXTURES_DIR / "vulnerable_sample.py").read_text()

        findings = await agent.analyze(code, "auth.py")

        assert all(f.category == Category.SECURITY for f in findings)

    @pytest.mark.asyncio
    async def test_findings_have_agent_name_set(self) -> None:
        """The SecurityAgent stamps its name on all returned findings."""
        agent = self._make_agent(chroma_docs=["CWE-89"])
        code = (FIXTURES_DIR / "vulnerable_sample.py").read_text()

        findings = await agent.analyze(code, "auth.py")

        assert all(f.agent_name == AGENT_SECURITY for f in findings)
        assert AGENT_SECURITY == "security"

    @pytest.mark.asyncio
    async def test_severity_and_cwe_preserved(self) -> None:
        """Severity and CWE ID are correctly passed through from LLM response."""
        agent = self._make_agent(chroma_docs=["CWE-89"])
        code = (FIXTURES_DIR / "vulnerable_sample.py").read_text()

        findings = await agent.analyze(code, "src/auth.py")

        severities = [f.severity for f in findings]
        cwes = [f.cwe_id for f in findings]

        assert Severity.CRITICAL in severities
        assert Severity.HIGH in severities
        assert Severity.MEDIUM in severities
        assert "CWE-89" in cwes
        assert "CWE-798" in cwes
        assert "CWE-327" in cwes

    @pytest.mark.asyncio
    async def test_findings_have_location_set(self) -> None:
        """Each finding's location.file_path matches the analyzed file."""
        agent = self._make_agent(chroma_docs=["CWE-89"])
        code = (FIXTURES_DIR / "vulnerable_sample.py").read_text()

        findings = await agent.analyze(code, "services/auth.py")

        assert all(f.location.file_path == "services/auth.py" for f in findings)

    # ── RAG context integration ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_rag_context_passed_to_llm(self) -> None:
        """The RAG context is included in the prompt sent to the LLM."""
        chroma_docs = ["CWE-89: use parameterized SQL queries."]
        fake_llm = FakeLLMService([])
        retriever = SecurityRetriever(top_k=1)
        retriever._query_chromadb = lambda _q: chroma_docs
        agent = SecurityAgent(llm=fake_llm, retriever=retriever)

        await agent.analyze("SELECT * FROM users WHERE id = " + "x", "db.py")

        prompt = fake_llm.complete_calls[0]
        assert "CWE-89" in prompt
        assert "parameterized" in prompt
        assert "db.py" in prompt

    @pytest.mark.asyncio
    async def test_rag_context_includes_file_path_in_prompt(self) -> None:
        """The prompt includes the file path being analyzed."""
        fake_llm = FakeLLMService([])
        retriever = SecurityRetriever(top_k=3)
        retriever._query_chromadb = lambda _q: []
        agent = SecurityAgent(llm=fake_llm, retriever=retriever)

        await agent.analyze("code", "src/views/login.py")

        prompt = fake_llm.complete_calls[0]
        assert "src/views/login.py" in prompt

    # ── BaseAgent.run() integration ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_run_iterates_over_multiple_files(self) -> None:
        """BaseAgent.run() processes multiple files and aggregates findings."""
        agent = self._make_agent(chroma_docs=["CWE-89"])
        files = {
            "a.py": "print(1)",
            "b.py": "print(2)",
        }

        findings = await agent.run(files)

        # Fake LLM returns the golden file (3 findings) per file, so 6 total
        assert len(findings) == 6
        assert all(f.agent_name == "security" for f in findings)

    @pytest.mark.asyncio
    async def test_run_skips_non_source_files(self) -> None:
        """BaseAgent.run() skips files without recognised source extensions."""
        simple_payload = [
            {"title": "Test", "description": "desc", "severity": "low"}
        ]
        agent = self._make_agent(llm_payload=simple_payload,
                                 chroma_docs=["CWE-89"])
        files = {
            "readme.md": "# Project",
            "image.png": "binary",
            "main.py": "print(1)",
        }

        findings = await agent.run(files)

        # Only main.py is a source file
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_run_isolates_per_file_failures(self) -> None:
        """One file failing does not prevent other files from being analyzed."""
        good_payload = [{"title": "Ok", "description": "desc", "severity": "low"}]
        agent = self._make_agent(llm_payload=good_payload,
                                 chroma_docs=["CWE-89"])

        # Make the agent's analyze() raise for a specific file
        original_analyze = agent.analyze
        async def selective_fail(code: str, file_path: str, context: dict | None = None) -> list[Finding]:  # noqa: E501
            if "bad" in file_path:
                raise RuntimeError("simulated failure")
            return await original_analyze(code, file_path, context)

        agent.analyze = selective_fail  # type: ignore[method-assign]

        files = {
            "good_a.py": "print(1)",
            "bad_file.py": "raise Exception",
            "good_b.py": "print(2)",
        }

        findings = await agent.run(files)

        # Only the two good files produce findings
        assert len(findings) == 2


class TestFakeLLMService:
    """Meta-tests ensuring the FakeLLMService behaves like a real one."""

    @pytest.mark.asyncio
    async def test_complete_json_parses_raw_json(self) -> None:
        """complete_json correctly parses a JSON string via _extract_json."""
        fake = FakeLLMService([{"a": 1}])
        result = await fake.complete_json("prompt")
        assert result == [{"a": 1}]

    @pytest.mark.asyncio
    async def test_complete_json_handles_non_json_text(self) -> None:
        """complete_json returns [] when the text isn't parseable JSON."""
        fake = FakeLLMService("sorry, I can't do that")
        result = await fake.complete_json("prompt")
        assert result == []

    @pytest.mark.asyncio
    async def test_complete_records_prompt(self) -> None:
        """complete() records the prompt for later assertion."""
        fake = FakeLLMService([])
        await fake.complete("test prompt")
        assert fake.complete_calls == ["test prompt"]


class TestGoldenFileConsistency:
    """Smoke tests verifying the golden-file fixtures are internally consistent."""

    def test_golden_llm_response_is_valid_json(self) -> None:
        """The stored fixture is valid JSON and parseable."""
        payload = _load_fixture_json("security_llm_response.json")
        assert isinstance(payload, list)
        assert len(payload) == 3

    def test_golden_findings_have_required_fields(self) -> None:
        """Every item in the golden fixture has title and description."""
        payload = _load_fixture_json("security_llm_response.json")
        for item in payload:
            assert "title" in item
            assert "description" in item
            assert "severity" in item

    def test_golden_vulnerable_sample_has_expected_vulns(self) -> None:
        """The vulnerable sample fixture actually contains the patterns we test for."""
        code = (FIXTURES_DIR / "vulnerable_sample.py").read_text()
        assert "sk_live_" in code  # hardcoded secret
        assert "f\"SELECT" in code or "f'SELECT" in code  # SQL injection pattern
        assert "hashlib.md5" in code  # weak crypto

    def test_golden_roundtrip_produces_valid_findings(self) -> None:
        """The golden-file LLM response parses into well-formed Finding objects."""
        payload = _load_fixture_json("security_llm_response.json")
        findings = findings_from_llm(payload, Category.SECURITY, "test.py")

        assert len(findings) == 3
        for f in findings:
            assert isinstance(f, Finding)
            assert f.title
            assert f.description
            assert f.severity in Severity
            assert f.confidence in Confidence
            assert f.category == Category.SECURITY
            assert f.location.file_path == "test.py"
