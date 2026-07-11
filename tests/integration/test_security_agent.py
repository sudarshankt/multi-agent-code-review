"""Integration tests for the SecurityAgent with a real LLM.

These tests require:
- LLM_API_KEY set in the environment or .env file
- Network access to the LLM API

Run manually or as a nightly gate (not on every CI push due to cost/latency).
Assertions are flexible because LLM output is non-deterministic.

Usage:
    uv run pytest tests/integration/test_security_agent.py -v -s
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.security.agent import SecurityAgent
from src.agents.security.retriever import SecurityRetriever
from src.models.finding import Category, Severity

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def vulnerable_files() -> dict[str, str]:
    """Return a single-file dict with the known-vulnerable Python code."""
    path = TEST_DATA_DIR / "app_vunerable.py"
    if not path.exists():
        pytest.skip(f"Test data file not found: {path}")
    return {"app_vunerable.py": path.read_text()}


@pytest.fixture
def security_agent() -> SecurityAgent:
    """Return a SecurityAgent wired to the real LLM."""
    return SecurityAgent()


# ── Tests ─────────────────────────────────────────────────────────────────

class TestSecurityAgentIntegration:
    """Real-LLM integration tests for the SecurityAgent."""

    @pytest.mark.asyncio
    async def test_finds_vulnerabilities_in_known_file(
        self,
        security_agent: SecurityAgent,
        vulnerable_files: dict[str, str],
    ) -> None:
        """Run the SecurityAgent against a file with known SQL injection,
        command injection, and hardcoded-secret patterns."""
        findings = await security_agent.run(vulnerable_files)

        assert isinstance(findings, list)

        if len(findings) == 0:
            pytest.fail(
                "SecurityAgent returned ZERO findings for a file containing "
                "SQL injection (f-string), OS command injection (os.system), "
                "and a hardcoded credential pattern. The agent or prompt may "
                "need tuning."
            )

        for finding in findings:
            assert finding.category == Category.SECURITY
            assert finding.agent_name == "security"
            assert finding.title
            assert finding.description
            assert finding.severity in Severity

        high_or_critical = [
            f for f in findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)
        ]
        assert len(high_or_critical) >= 1, (
            f"Expected >=1 high/critical finding, got {len(high_or_critical)}. "
            f"Findings: {[(f.title, f.severity.value) for f in findings]}"
        )

    @pytest.mark.asyncio
    async def test_includes_cwe_ids(
        self,
        security_agent: SecurityAgent,
        vulnerable_files: dict[str, str],
    ) -> None:
        """At least some findings should carry a CWE ID."""
        findings = await security_agent.run(vulnerable_files)
        if len(findings) == 0:
            pytest.skip("No findings — skipping CWE check")

        cwe_findings = [f for f in findings if f.cwe_id]
        assert len(cwe_findings) >= 1, (
            f"Expected >=1 finding with a CWE ID, got 0. "
            f"Titles: {[f.title for f in findings]}"
        )

    @pytest.mark.asyncio
    async def test_has_concrete_suggestions(
        self,
        security_agent: SecurityAgent,
        vulnerable_files: dict[str, str],
    ) -> None:
        """At least half of findings should include a fix suggestion."""
        findings = await security_agent.run(vulnerable_files)
        if len(findings) == 0:
            pytest.skip("No findings — skipping suggestions check")

        with_suggestions = [f for f in findings if f.suggestion]
        ratio = len(with_suggestions) / len(findings)
        assert ratio >= 0.5, (
            f"Only {len(with_suggestions)}/{len(findings)} have suggestions "
            f"(ratio={ratio:.0%}, expected >=50%)."
        )

    @pytest.mark.asyncio
    async def test_graceful_degradation_without_chromadb(
        self,
        vulnerable_files: dict[str, str],
    ) -> None:
        """Agent still produces findings when ChromaDB is unavailable."""
        retriever = SecurityRetriever(top_k=5)
        retriever._query_chromadb = lambda _q: []  # type: ignore[method-assign]
        from src.services.llm_service import get_llm_service

        agent = SecurityAgent(llm=get_llm_service(), retriever=retriever)
        findings = await agent.run(vulnerable_files)

        assert isinstance(findings, list)
        if len(findings) == 0:
            pytest.fail(
                "SecurityAgent returned ZERO findings with fallback knowledge. "
                "The fallback path may be broken."
            )

    @pytest.mark.asyncio
    async def test_clean_code_returns_no_high_findings(
        self,
        security_agent: SecurityAgent,
    ) -> None:
        """Clean, safe code should not trigger HIGH/CRITICAL findings."""
        clean_code = (
            '"""A simple utility module with no security issues."""\n'
            "import os\n"
            "import json\n"
            "from pathlib import Path\n\n\n"
            "def read_config(path: str) -> dict:\n"
            '    """Read a JSON config file safely."""\n'
            "    resolved = Path(path).resolve()\n"
            "    if not resolved.exists():\n"
            "        return {}\n"
            "    with open(resolved, 'r') as f:\n"
            "        return json.load(f)\n\n\n"
            "def add(a: int, b: int) -> int:\n"
            '    """Add two integers."""\n'
            "    return a + b\n"
        )

        findings = await security_agent.run({"clean.py": clean_code})

        high_or_critical = [
            f for f in findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)
        ]
        assert len(high_or_critical) == 0, (
            f"Clean code produced HIGH/CRITICAL findings: "
            f"{[(f.title, f.severity.value) for f in high_or_critical]}"
        )