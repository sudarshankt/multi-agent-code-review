"""Helpers to turn raw LLM JSON into validated Finding objects."""

from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.models.finding import Category, Confidence, Finding, FindingSource, Location, Severity

logger = get_logger(__name__)

_SEVERITY_ALIASES = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "moderate": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
    "informational": Severity.INFO,
}

_CONFIDENCE_ALIASES = {
    "high": Confidence.HIGH,
    "medium": Confidence.MEDIUM,
    "low": Confidence.LOW,
}


def _coerce_severity(value: Any) -> Severity:
    return _SEVERITY_ALIASES.get(str(value).strip().lower(), Severity.MEDIUM)


def _coerce_confidence(value: Any) -> Confidence:
    return _CONFIDENCE_ALIASES.get(str(value).strip().lower(), Confidence.MEDIUM)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def finding_from_dict(item: dict[str, Any], category: Category, file_path: str) -> Finding | None:
    """Build a Finding from one LLM result dict, or None if unusable."""
    if not isinstance(item, dict):
        return None
    title = item.get("title") or item.get("name") or item.get("issue")
    description = item.get("description") or item.get("detail") or item.get("message")
    if not title and not description:
        return None
    title = str(title or description)[:200]
    description = str(description or title)

    location = Location(
        file_path=item.get("file_path") or file_path,
        start_line=_coerce_int(item.get("start_line") or item.get("line")),
        end_line=_coerce_int(item.get("end_line")),
        snippet=item.get("snippet"),
    )
    return Finding(
        category=category,
        severity=_coerce_severity(item.get("severity")),
        confidence=_coerce_confidence(item.get("confidence")),
        title=title,
        description=description,
        location=location,
        suggestion=item.get("suggestion") or item.get("fix"),
        references=_as_list(item.get("references")),
        cwe_id=item.get("cwe_id") or item.get("cwe"),
        source=FindingSource.LLM,  # LLM-generated findings
    )


def findings_from_llm(
    payload: Any, category: Category, file_path: str
) -> list[Finding]:
    """Normalise an LLM JSON payload (list, or {findings:[...]}) into Findings."""
    items: list[Any]
    if isinstance(payload, dict):
        items = payload.get("findings") or payload.get("issues") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    findings: list[Finding] = []
    for item in items:
        finding = finding_from_dict(item, category, file_path)
        if finding is not None:
            findings.append(finding)
    return findings
