"""Unit tests for LLM response parsing — findings_from_llm and finding_from_dict."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.parsing import findings_from_llm
from src.models.finding import Category, Confidence, Finding, Severity

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> object:
    path = FIXTURES_DIR / name
    if path.suffix == ".json":
        return json.loads(path.read_text())
    return path.read_text()


class TestFindingsFromLLM:
    """Tests for findings_from_llm covering various payload shapes and edge cases."""

    # ── valid payload shapes ──────────────────────────────────────────────

    def test_parse_list_payload(self) -> None:
        """A plain JSON list produces the correct number of Finding objects."""
        payload = _load_fixture("security_llm_response.json")
        findings = findings_from_llm(payload, Category.SECURITY, "test.py")

        assert len(findings) == 3
        assert all(isinstance(f, Finding) for f in findings)
        assert all(f.category == Category.SECURITY for f in findings)

    def test_parse_dict_wrapped_with_findings_key(self) -> None:
        """A dict with a 'findings' key is unwrapped correctly."""
        items = [
            {
                "title": "XSS in template",
                "description": "Unescaped user input in HTML",
                "severity": "high",
                "confidence": "high",
                "cwe_id": "CWE-79",
            }
        ]
        payload = {"findings": items}
        findings = findings_from_llm(payload, Category.SECURITY, "view.html")

        assert len(findings) == 1
        assert findings[0].title == "XSS in template"
        assert findings[0].cwe_id == "CWE-79"

    def test_parse_dict_wrapped_with_issues_key(self) -> None:
        """A dict with an 'issues' key (alternative wrapper) works too."""
        items = [
            {
                "title": "Hardcoded token",
                "description": "Token in source",
                "severity": "medium",
            }
        ]
        payload = {"issues": items}
        findings = findings_from_llm(payload, Category.SECURITY, "config.py")

        assert len(findings) == 1
        assert findings[0].title == "Hardcoded token"

    def test_parse_empty_list(self) -> None:
        """An empty list returns no findings."""
        findings = findings_from_llm([], Category.SECURITY, "clean.py")
        assert findings == []

    def test_parse_empty_dict(self) -> None:
        """An empty dict returns no findings."""
        findings = findings_from_llm({}, Category.SECURITY, "clean.py")
        assert findings == []

    # ── non-standard types ────────────────────────────────────────────────

    def test_parse_non_list_non_dict_returns_empty(self) -> None:
        """A string or int payload returns an empty list gracefully."""
        assert findings_from_llm("gibberish", Category.SECURITY, "f.py") == []
        assert findings_from_llm(42, Category.SECURITY, "f.py") == []
        assert findings_from_llm(None, Category.SECURITY, "f.py") == []

    # ── severity coercion ─────────────────────────────────────────────────

    def test_severity_coercion(self) -> None:
        """Severity strings (including aliases like 'moderate') map correctly."""
        payload = [
            {"title": "t", "description": "d", "severity": "critical"},
            {"title": "t", "description": "d", "severity": "HIGH"},
            {"title": "t", "description": "d", "severity": "moderate"},
            {"title": "t", "description": "d", "severity": "info"},
            {"title": "t", "description": "d", "severity": "informational"},
            {"title": "t", "description": "d", "severity": "low"},
        ]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        sevs = [f.severity for f in findings]

        assert sevs == [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,  # moderate → medium
            Severity.INFO,
            Severity.INFO,  # informational → info
            Severity.LOW,
        ]

    def test_unknown_severity_defaults_to_medium(self) -> None:
        """An unrecognized severity string defaults to MEDIUM."""
        payload = [{"title": "t", "description": "d", "severity": "super-bad"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].severity == Severity.MEDIUM

    def test_missing_severity_defaults_to_medium(self) -> None:
        """When severity is absent, it defaults to MEDIUM."""
        payload = [{"title": "t", "description": "d"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].severity == Severity.MEDIUM

    # ── confidence coercion ───────────────────────────────────────────────

    def test_confidence_coercion(self) -> None:
        """Confidence strings map correctly."""
        payload = [
            {"title": "t", "description": "d", "confidence": "high"},
            {"title": "t", "description": "d", "confidence": "MEDIUM"},
            {"title": "t", "description": "d", "confidence": "low"},
        ]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        confs = [f.confidence for f in findings]

        assert confs == [Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW]

    # ── title / description fallback ──────────────────────────────────────

    def test_title_falls_back_to_name_and_issue(self) -> None:
        """Title is extracted from 'name' or 'issue' if 'title' is missing."""
        payload = [
            {"name": "Name fallback", "description": "desc"},
            {"issue": "Issue fallback", "description": "desc2"},
        ]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].title == "Name fallback"
        assert findings[1].title == "Issue fallback"

    def test_description_falls_back_to_detail_and_message(self) -> None:
        """Description falls back to 'detail' or 'message' if absent."""
        payload = [
            {"title": "t1", "detail": "detail text"},
            {"title": "t2", "message": "message text"},
        ]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].description == "detail text"
        assert findings[1].description == "message text"

    def test_item_without_title_or_description_is_skipped(self) -> None:
        """Items lacking both title and description are filtered out."""
        payload = [
            {"title": "Valid", "description": "d"},
            {"severity": "high"},  # no title or description
            {"title": "Also valid", "description": "d2"},
        ]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert len(findings) == 2
        assert findings[0].title == "Valid"
        assert findings[1].title == "Also valid"

    def test_non_dict_items_are_skipped(self) -> None:
        """Non-dict items in the list are silently ignored."""
        payload = ["not a dict", 123, {"title": "ok", "description": "d"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert len(findings) == 1
        assert findings[0].title == "ok"

    # ── title truncation ──────────────────────────────────────────────────

    def test_title_truncated_to_200_chars(self) -> None:
        """Titles longer than 200 characters are truncated."""
        long_title = "A" * 250
        payload = [{"title": long_title, "description": "desc"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert len(findings[0].title) == 200

    def test_title_from_description_when_title_missing(self) -> None:
        """When title is absent, description is used as title."""
        payload = [{"description": "Used as title"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].title == "Used as title"
        assert findings[0].description == "Used as title"

    # ── location fields ───────────────────────────────────────────────────

    def test_location_fields_mapped_correctly(self) -> None:
        """Line numbers, file_path, and snippet are mapped to Location."""
        payload = [
            {
                "title": "SQLi",
                "description": "sql injection",
                "start_line": 10,
                "end_line": 15,
                "snippet": "cursor.execute(f\"SELECT ...\")",
            }
        ]
        findings = findings_from_llm(payload, Category.SECURITY, "src/db.py")
        loc = findings[0].location
        assert loc.file_path == "src/db.py"
        assert loc.start_line == 10
        assert loc.end_line == 15
        assert loc.snippet == 'cursor.execute(f"SELECT ...")'

    def test_line_number_from_line_fallback(self) -> None:
        """'line' is used as start_line when 'start_line' is missing."""
        payload = [{"title": "t", "description": "d", "line": 42}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].location.start_line == 42

    def test_file_path_from_payload_overrides_arg(self) -> None:
        """If a finding specifies its own file_path, it takes precedence."""
        payload = [
            {
                "title": "t",
                "description": "d",
                "file_path": "other/path.py",
            }
        ]
        findings = findings_from_llm(payload, Category.SECURITY, "default.py")
        assert findings[0].location.file_path == "other/path.py"

    # ── suggestion / fix ──────────────────────────────────────────────────

    def test_suggestion_falls_back_to_fix(self) -> None:
        """'fix' field is used when 'suggestion' is absent."""
        payload = [{"title": "t", "description": "d", "fix": "Use params instead"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].suggestion == "Use params instead"

    # ── references ────────────────────────────────────────────────────────

    def test_references_single_string_is_wrapped_in_list(self) -> None:
        """A single string reference becomes a one-element list."""
        payload = [
            {
                "title": "t",
                "description": "d",
                "references": "https://example.com",
            }
        ]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].references == ["https://example.com"]

    def test_references_list_is_preserved(self) -> None:
        """A list of references is preserved as-is."""
        refs = ["https://a.com", "https://b.com"]
        payload = [{"title": "t", "description": "d", "references": refs}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].references == refs

    def test_references_none_is_empty_list(self) -> None:
        """Missing references results in an empty list."""
        payload = [{"title": "t", "description": "d"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].references == []

    # ── CWE ID ────────────────────────────────────────────────────────────

    def test_cwe_id_falls_back_to_cwe_field(self) -> None:
        """'cwe' field is used when 'cwe_id' is absent."""
        payload = [{"title": "t", "description": "d", "cwe": "CWE-22"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].cwe_id == "CWE-22"

    def test_missing_cwe_id_is_none(self) -> None:
        """When no CWE info is present, cwe_id is None."""
        payload = [{"title": "t", "description": "d"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].cwe_id is None

    # ── source field ──────────────────────────────────────────────────────

    def test_source_is_always_llm(self) -> None:
        """findings_from_llm always sets source to FindingSource.LLM."""
        payload = [{"title": "t", "description": "d"}]
        findings = findings_from_llm(payload, Category.SECURITY, "f.py")
        assert findings[0].source.value == "llm"

    # ── golden-file roundtrip ─────────────────────────────────────────────

    def test_golden_file_roundtrip(self) -> None:
        """The saved golden-file fixture produces consistent Finding objects."""
        payload = _load_fixture("security_llm_response.json")
        findings = findings_from_llm(payload, Category.SECURITY, "src/auth.py")

        assert len(findings) == 3

        # SQL Injection (critical)
        sqli = findings[0]
        assert sqli.title == "SQL Injection via string formatting in execute()"
        assert sqli.severity == Severity.CRITICAL
        assert sqli.confidence == Confidence.HIGH
        assert sqli.cwe_id == "CWE-89"
        assert sqli.location.start_line == 12
        assert sqli.location.end_line == 14
        assert "parameterized" in (sqli.suggestion or "")

        # Hardcoded secret (high)
        secret = findings[1]
        assert secret.severity == Severity.HIGH
        assert secret.cwe_id == "CWE-798"

        # Weak crypto (medium)
        crypto = findings[2]
        assert crypto.severity == Severity.MEDIUM
        assert crypto.cwe_id == "CWE-327"
