# Purpose: Validates StyleAgent._run_ruff() with mocked subprocess.
"""Unit tests for StyleAgent._run_ruff() — ruff invocation and output parsing.

These tests verify:
- Normal ruff output is parsed into Finding objects
- Finding objects have the correct source, category, severity, and location
- Error conditions (FileNotFoundError, timeout, bad JSON) are handled gracefully
- Non-dict items in ruff output are skipped
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

from src.agents.style.agent import StyleAgent
from src.models.finding import FindingSource, Severity


class TestRunRuff:
    """Tests for StyleAgent._run_ruff()."""

    @staticmethod
    def _make_ruff_output(items: list[tuple[str, str, int]]) -> list[dict]:
        return [
            {"code": code, "message": msg, "location": {"row": line, "column": 1}}
            for code, msg, line in items
        ]

    def test_parses_multiple_ruff_findings(self) -> None:
        """Multiple ruff issues are all returned as Finding objects."""
        ruff_raw = self._make_ruff_output([
            ("F401", "`os` imported but unused", 1),
            ("W292", "No newline at end of file", 5),
            ("E501", "Line too long (120 > 100)", 10),
        ])

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("import os\n\nprint('hello' * 200)", "test.py")

        assert len(findings) == 3

    def test_findings_have_linter_source(self) -> None:
        """All ruff findings must have source=FindingSource.LINTER."""
        ruff_raw = self._make_ruff_output([("F401", "`sys` imported but unused", 1)])

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("import sys\n", "mod.py")

        assert len(findings) == 1
        assert findings[0].source == FindingSource.LINTER

    def test_findings_have_low_severity(self) -> None:
        """All ruff findings have severity LOW."""
        ruff_raw = self._make_ruff_output([("F401", "unused", 1)])

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("import json\n", "f.py")

        assert findings[0].severity == Severity.LOW

    def test_title_format_is_code_colon_message(self) -> None:
        """Ruff finding title is formatted as 'CODE: message'."""
        ruff_raw = self._make_ruff_output([("W293", "Blank line contains whitespace", 3)])

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("   \n", "ws.py")

        assert findings[0].title == "W293: Blank line contains whitespace"

    def test_location_has_correct_file_path_and_line(self) -> None:
        """Ruff finding location matches the file_path and line from ruff output."""
        ruff_raw = self._make_ruff_output([("F401", "`os` imported but unused", 42)])

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("import os\n", "src/app.py")

        loc = findings[0].location
        assert loc.file_path == "src/app.py"
        assert loc.start_line == 42
        assert loc.end_line == 42

    def test_empty_ruff_output_returns_empty_list(self) -> None:
        """When ruff returns an empty JSON array, no findings are produced."""
        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = b"[]"
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("print('hello')\n", "clean.py")

        assert findings == []

    # ── error paths ───────────────────────────────────────────────────────

    def test_ruff_not_found_returns_empty(self) -> None:
        """When ruff binary is not found, an empty list is returned."""
        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            findings = agent._run_ruff("code", "file.py")

        assert findings == []

    def test_ruff_timeout_returns_empty(self) -> None:
        """When ruff times out, an empty list is returned."""
        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruff", 10)):
            findings = agent._run_ruff("large code", "big.py")

        assert findings == []

    def test_malformed_json_returns_empty(self) -> None:
        """When ruff output is not valid JSON, an empty list is returned."""
        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = b"not json at all"
            mock_run.return_value.stderr = b"ruf error"

            findings = agent._run_ruff("code", "bad.py")

        assert findings == []

    def test_empty_stdout_returns_empty(self) -> None:
        """When ruff produces empty stdout, an empty list is returned."""
        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = b""
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("code", "silent.py")

        assert findings == []

    # ── edge cases ────────────────────────────────────────────────────────

    def test_skips_non_dict_items(self) -> None:
        """Non-dict items in ruff's JSON array are silently skipped."""
        ruff_raw = [
            "not a dict",
            42,
            {"code": "F401", "message": "unused import", "location": {"row": 1, "column": 1}},
            None,
        ]

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("import sys\n", "skip.py")

        assert len(findings) == 1
        assert "F401" in findings[0].title

    def test_skips_items_without_line_number(self) -> None:
        """Ruff items without a row number are skipped."""
        ruff_raw = [
            {"code": "F401", "message": "no line", "location": {"column": 1}},
            {"code": "W292", "message": "has line", "location": {"row": 5, "column": 1}},
        ]

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("code", "nolines.py")

        assert len(findings) == 1
        assert findings[0].location.start_line == 5

    def test_code_falls_back_to_question_mark(self) -> None:
        """When ruff item has no 'code' field, title uses '?'."""
        ruff_raw = [
            {"message": "Something wrong", "location": {"row": 1, "column": 1}},
        ]

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("code", "nocode.py")

        assert len(findings) == 1
        assert findings[0].title.startswith("?: ")

    def test_message_truncated_to_50_chars_in_title(self) -> None:
        """Long ruff messages are truncated to 50 characters in the title."""
        long_msg = "A" * 80
        ruff_raw = [
            {"code": "F999", "message": long_msg, "location": {"row": 1, "column": 1}},
        ]

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("code", "long.py")

        title = findings[0].title
        # Title format: "F999: " + first 50 chars
        assert len(title) <= 56  # "F999: " (6) + 50
        assert title.startswith("F999: ")

    def test_full_message_in_description(self) -> None:
        """The full, untruncated ruff message is stored in description."""
        long_msg = "This is a very long message that exceeds fifty characters easily"
        ruff_raw = [
            {"code": "W999", "message": long_msg, "location": {"row": 3, "column": 1}},
        ]

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b""

            findings = agent._run_ruff("code", "desc.py")

        assert findings[0].description == long_msg

    def test_stderr_is_ignored(self) -> None:
        """Ruff writing to stderr does not affect the parsed output."""
        ruff_raw = self._make_ruff_output([("F401", "unused", 1)])

        agent = StyleAgent.__new__(StyleAgent)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = json.dumps(ruff_raw).encode()
            mock_run.return_value.stderr = b"warning: some deprecation notice"

            findings = agent._run_ruff("import os\n", "stderr.py")

        assert len(findings) == 1
