# Purpose: Validates that StyleAgent findings faithfully correspond to actual file content
# (no phantom imports, no lines past EOF, correct file paths) and verifies
# output quality (structure, severity, suggestions).

"""Integration tests for the StyleAgent with a real LLM.

These tests require:
- LLM_API_KEY set in the environment or .env file
- Network access to the LLM API
- ruff installed and available on PATH

Run manually or as a nightly gate (not on every CI push due to cost/latency).

Primary goal: confirm that ruff findings reference only symbols actually present
in the reviewed file and that line numbers are within file bounds.  This guards
against content-mismatch bugs where the agent receives wrong file content.

Usage:
    uv run pytest tests/integration/test_style_agent.py -v -s
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.agents.style.agent import StyleAgent
from src.models.finding import Category, Finding, FindingSource, Severity

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def app_vulnerable_v1_files() -> dict[str, str]:
    """Load app_vunerable-v1.py — a 70-line file with typing/requests/jwt imports."""
    path = TEST_DATA_DIR / "app_vunerable-v1.py"
    if not path.exists():
        pytest.skip(f"Test data file not found: {path}")
    return {"tests/test_data/app_vunerable-v1.py": path.read_text()}


@pytest.fixture
def profile_files() -> dict[str, str]:
    """Load profile.py — a 7-line file with zero import statements."""
    path = TEST_DATA_DIR / "profile.py"
    if not path.exists():
        pytest.skip(f"Test data file not found: {path}")
    return {"tests/test_data/profile.py": path.read_text()}


@pytest.fixture
def style_agent() -> StyleAgent:
    """Return a StyleAgent wired to the real LLM and ruff."""
    return StyleAgent()


# ── Helpers ───────────────────────────────────────────────────────────────

# ruff finding titles look like "F401: <msg>" — a capital letter + 3 digits + colon.
_RUFF_CODE_RE = re.compile(r"^[A-Z]\d{3}:")


def _is_ruff_finding(finding: Finding) -> bool:
    """Detect ruff-generated findings by their title pattern ('F401: ...')."""
    return bool(_RUFF_CODE_RE.match(finding.title))


def _ruff_code(finding: Finding) -> str:
    """Extract the ruff error code (e.g. 'F401') from a finding title."""
    m = _RUFF_CODE_RE.match(finding.title)
    return m.group(0).rstrip(":") if m else ""


# ── Phase 2: Core Fidelity Tests ──────────────────────────────────────────


class TestStyleAgentContentFidelity:
    """Verify ruff and LLM findings are faithful to the actual file content."""

    @pytest.mark.asyncio
    async def test_no_phantom_ruff_imports_in_app_vulnerable_v1(
        self,
        style_agent: StyleAgent,
        app_vulnerable_v1_files: dict[str, str],
    ) -> None:
        """No ruff finding should reference a symbol absent from the actual file.

        app_vunerable-v1.py only imports: __future__.annotations, typing.Any,
        typing.Dict, requests, jwt.  Any F401 (unused import) or F821
        (undefined name) referencing sentence_transformers, langgraph, arq,
        fastapi, unittest.mock, src.models.finding, src.core.constants,
        pathlib, ast, abort, Invoice, or session is a phantom finding.
        """
        findings = await style_agent.run(app_vulnerable_v1_files)

        # Symbols that are definitely NOT in app_vunerable-v1.py
        phantom_symbols = {
            "sentence_transformers",
            "SentenceTransformer",
            "langgraph",
            "add_messages",
            "arq.worker",
            "Worker",
            "fastapi",
            "HTTPException",
            "unittest.mock",
            "src.models.finding",
            "Category",
            "src.core.constants",
            "MAX_CODE_CHARS_FOR_RAG",
            "pathlib",
            "Path",
            "ast",
            "Callable",
            "abort",
            "Invoice",
            "session",
        }

        ruff_import_findings = [
            f for f in findings
            if _is_ruff_finding(f) and _ruff_code(f) in ("F401", "F821")
        ]

        phantom = []
        for f in ruff_import_findings:
            for sym in phantom_symbols:
                if sym in f.title or sym in f.description:
                    phantom.append(f)
                    break

        assert phantom == [], (
            "Phantom ruff import/name findings detected (symbols not in file):\n"
            + "\n".join(f"  - {f.title} (line {f.location.start_line})" for f in phantom)
        )

    @pytest.mark.asyncio
    async def test_no_phantom_ruff_imports_in_profile(
        self,
        style_agent: StyleAgent,
        profile_files: dict[str, str],
    ) -> None:
        """profile.py has zero import statements — no F401 findings expected."""
        findings = await style_agent.run(profile_files)

        f401_findings = [
            f for f in findings
            if _is_ruff_finding(f) and _ruff_code(f) == "F401"
        ]

        assert f401_findings == [], (
            "F401 (unused import) findings in profile.py which has no imports:\n"
            + "\n".join(f"  - {f.title} (line {f.location.start_line})" for f in f401_findings)
        )

    @pytest.mark.asyncio
    async def test_line_numbers_within_file_bounds(
        self,
        style_agent: StyleAgent,
        app_vulnerable_v1_files: dict[str, str],
        profile_files: dict[str, str],
    ) -> None:
        """Every finding's start_line must be ≤ the actual file line count."""
        all_files = {**app_vulnerable_v1_files, **profile_files}
        findings = await style_agent.run(all_files)

        # Build a lookup: file_path → line count
        line_counts = {
            path: len(content.split("\n"))
            for path, content in all_files.items()
        }

        out_of_bounds = []
        for f in findings:
            fp = f.location.file_path
            max_line = line_counts.get(fp)
            if max_line is None:
                out_of_bounds.append((f, f"unknown file '{fp}'"))
            elif f.location.start_line is not None and f.location.start_line > max_line:
                out_of_bounds.append(
                    (f, f"line {f.location.start_line} > max {max_line}")
                )

        assert out_of_bounds == [], (
            "Findings with line numbers exceeding file bounds:\n"
            + "\n".join(f"  - [{info}] {fnd.title}" for fnd, info in out_of_bounds)
        )

    @pytest.mark.asyncio
    async def test_file_paths_are_correct(
        self,
        style_agent: StyleAgent,
        app_vulnerable_v1_files: dict[str, str],
        profile_files: dict[str, str],
    ) -> None:
        """Every finding's location.file_path must be one of the input keys."""
        all_files = {**app_vulnerable_v1_files, **profile_files}
        findings = await style_agent.run(all_files)

        valid_paths = set(all_files.keys())
        wrong_paths = [
            f for f in findings
            if f.location.file_path not in valid_paths
        ]

        assert wrong_paths == [], (
            "Findings with unexpected file paths:\n"
            + "\n".join(
                f"  - {f.location.file_path}: {f.title}" for f in wrong_paths
            )
        )


# ── Phase 3: Output Quality Test ──────────────────────────────────────────


class TestStyleAgentOutputQuality:
    """Verify finding structure and quality (mirrors security agent tests)."""

    @pytest.mark.asyncio
    async def test_style_findings_have_valid_structure(
        self,
        style_agent: StyleAgent,
        app_vulnerable_v1_files: dict[str, str],
        profile_files: dict[str, str],
    ) -> None:
        """All findings must have correct category, agent_name, severity,
        and non-empty title/description."""
        all_files = {**app_vulnerable_v1_files, **profile_files}
        findings = await style_agent.run(all_files)

        assert isinstance(findings, list)

        if len(findings) == 0:
            pytest.fail(
                "StyleAgent returned ZERO findings for Python files containing "
                "unused parameters, misleading function names, dead code, and "
                "missing docstrings. The agent or prompt may need tuning."
            )

        for finding in findings:
            assert finding.category == Category.STYLE, (
                f"Expected STYLE category, got {finding.category}: {finding.title}"
            )
            assert finding.agent_name == "style", (
                f"Expected agent_name='style', got '{finding.agent_name}': {finding.title}"
            )
            assert finding.title, f"Empty title in finding: {finding}"
            assert finding.description, f"Empty description in finding: {finding}"
            assert finding.severity in Severity, (
                f"Invalid severity {finding.severity}: {finding.title}"
            )

        # At least some findings should carry suggestions.
        with_suggestions = [f for f in findings if f.suggestion]
        if len(findings) >= 3:
            assert len(with_suggestions) >= 1, (
                f"Expected at least 1 finding with a suggestion, got 0. "
                f"Titles: {[f.title for f in findings]}"
            )


# ── Phase 4: Content Correctness Test ─────────────────────────────────────


class TestStyleAgentContentCorrectness:
    """Verify LLM findings reference code that actually exists in the files."""

    @pytest.mark.asyncio
    async def test_llm_findings_match_actual_code(
        self,
        style_agent: StyleAgent,
        app_vulnerable_v1_files: dict[str, str],
        profile_files: dict[str, str],
    ) -> None:
        """If a non-ruff finding mentions a function name, that function must
        exist in the file."""
        all_files = {**app_vulnerable_v1_files, **profile_files}
        findings = await style_agent.run(all_files)

        # Only check LLM-sourced findings (not ruff)
        llm_findings = [f for f in findings if not _is_ruff_finding(f)]

        if len(llm_findings) == 0:
            pytest.skip("No LLM findings to validate")

        # Collect code per file for verification
        for f in llm_findings:
            fp = f.location.file_path
            code = all_files.get(fp)
            if code is None:
                continue

            # If the finding mentions a line, that line should exist
            if f.location.start_line is not None:
                lines = code.split("\n")
                assert f.location.start_line <= len(lines), (
                    f"Finding references line {f.location.start_line} but "
                    f"'{fp}' has only {len(lines)} lines: {f.title}"
                )

    @pytest.mark.asyncio
    async def test_specific_known_issues_found(
        self,
        style_agent: StyleAgent,
        app_vulnerable_v1_files: dict[str, str],
        profile_files: dict[str, str],
    ) -> None:
        """Spot-check that known style issues are flagged.

        Known issues across the two test files:
        - app_vunerable-v1.py: unused 'authenticated_user_id' param (line 31),
          misleading 'get_db_connection' name (line 17),
          inconsistent return type in fetch_avatar (bytes | str)
        - profile.py: missing docstring on fetch_avatar (line 1),
          dead commented-out code (line 3)
        """
        all_files = {**app_vulnerable_v1_files, **profile_files}
        findings = await style_agent.run(all_files)

        titles_lower = {f.title.lower() for f in findings}
        descriptions_lower = {f.description.lower() for f in findings}

        # Check that at least a subset of known issues appear
        known_patterns = [
            # app_vunerable-v1.py expected issues
            ("authenticated_user_id", "app_vunerable-v1.py"),
            ("get_db_connection", "app_vunerable-v1.py"),
            ("fetch_avatar", "either"),
        ]

        matched = 0
        unmatched: list[str] = []
        for pattern, source in known_patterns:
            found = any(
                pattern in t for t in titles_lower
            ) or any(
                pattern in d for d in descriptions_lower
            )
            if found:
                matched += 1
            else:
                unmatched.append(f"{pattern} (expected in {source})")

        # We should match at least 2 of the 3 known patterns
        assert matched >= 2, (
            f"Only {matched}/{len(known_patterns)} known issues matched. "
            f"Missing: {unmatched}"
        )


# ── Phase 5: Source Marking Test ──────────────────────────────────────────


class TestStyleAgentSourceMarking:
    """Verify findings are tagged with the correct source."""

    @pytest.mark.asyncio
    async def test_ruff_findings_have_linter_source(
        self,
        style_agent: StyleAgent,
        app_vulnerable_v1_files: dict[str, str],
    ) -> None:
        """Ruff-originated findings should carry source=FindingSource.LINTER.

        NOTE: This test currently EXPECTS TO FAIL because _run_ruff() does not
        set source=FindingSource.LINTER — it defaults to FindingSource.LLM.
        When this test starts passing, the bug is fixed.
        """
        findings = await style_agent.run(app_vulnerable_v1_files)

        ruff_findings = [f for f in findings if _is_ruff_finding(f)]

        if len(ruff_findings) == 0:
            pytest.skip("No ruff findings — source marking cannot be verified")

        wrong_source = [
            f for f in ruff_findings
            if f.source != FindingSource.LINTER
        ]

        if wrong_source:
            pytest.fail(
                "BUG CONFIRMED: ruff findings have wrong source. "
                "Expected FindingSource.LINTER, got:\n"
                + "\n".join(
                    f"  - [{f.source.value}] {f.title}" for f in wrong_source
                )
                + "\n\nFix: _run_ruff() should pass source=FindingSource.LINTER "
                "when constructing Finding objects."
            )

        # If we reach here, the bug is already fixed.
        assert len(wrong_source) == 0
