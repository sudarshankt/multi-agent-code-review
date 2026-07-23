"""TestFixAgent: fix failing test files via LLM, preserving test coverage."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from src.core.logging import get_logger
from src.prompts.loader import render
from src.services.llm_service import LLMService, get_llm_service

logger = get_logger(__name__)

AGENT_TEST_FIX = "test_fix"


def _normalize_path(raw: str) -> str:
    """Convert an absolute or `../../` temp-dir path into a repo-relative path.

    Pytest output from a temp-dir clone looks like::

        /var/folders/.../pr-review-test-XXX/tests/unit/test_foo.py

    We strip the temp-dir prefix by looking for the LAST ``/tests/`` (or
    ``/test/``) segment — using the *last* occurrence avoids matching a
    ``tests`` directory that's part of the temp path itself.
    """
    if not raw:
        return raw

    # Resolve ../ segments to an absolute path, then strip the temp prefix.
    try:
        resolved = str(Path(raw).resolve()) if ".." in raw else raw
    except Exception:
        resolved = raw

    for marker in ("/tests/", "/test/"):
        idx = resolved.rfind(marker)  # rfind — last occurrence, not first
        if idx >= 0:
            return resolved[idx + 1:]  # "tests/unit/test_foo.py"

    # No standard test directory prefix — try to extract just the filename
    # and assume it lives under tests/.
    fname = Path(raw).name
    if fname and (fname.startswith("test_") or fname.endswith("_test.py")):
        return f"tests/{fname}"

    # Last resort: return as-is; _read_clone_file will log a warning if it
    # can't find the file.
    return raw


def parse_failing_files(pytest_output: str) -> dict[str, str]:
    """Extract {relative_path: failure_details} from pytest --tb=short output.

    Returned file paths are repo-relative (e.g. ``tests/unit/test_auth.py``)
    so they can be resolved against a fresh clone directory.

    Handles two output styles:

    1. Summary-line style (``-q`` flag):
       FAILED tests/test_auth.py::test_login - AssertionError: ...

    2. Section style (``--tb=short`` flag):
       ______________________ test_login _______________________
       tests/test_auth.py:42: in test_login
           assert 1 == 2
       E   AssertionError: ...
    """
    failures: dict[str, str] = {}

    # --- Style 1: "FAILED path/to/file.py::test_name" lines ---
    for m in re.finditer(r"^FAILED\s+(.+?)::(\S+)", pytest_output, re.MULTILINE):
        raw_path = m.group(1)
        file_path = _normalize_path(raw_path)
        rest = pytest_output[m.end():]
        if file_path not in failures:
            failures[file_path] = ""

    # --- Style 2: section headers "__________ test_name ___________" ---
    sections = re.split(r"^_{10,}\s+(.+?)\s+_{10,}$", pytest_output, flags=re.MULTILINE)
    for i in range(1, len(sections) - 1, 2):
        test_name = sections[i].strip()
        body = sections[i + 1]
        m = re.search(r"^(.+?\.py):\d+:", body, re.MULTILINE)
        if m:
            file_path = _normalize_path(m.group(1))
            if file_path not in failures:
                failures[file_path] = body.strip()
            else:
                failures[file_path] += "\n\n" + body.strip()

    # Deduplicate and trim each entry
    cleaned: dict[str, str] = {}
    for path in sorted(failures.keys()):
        cleaned[path] = failures[path][:4000] or pytest_output[:4000]

    return cleaned


class TestFixAgent:
    """Fixes failing test files via LLM. Does NOT modify source code."""

    name = AGENT_TEST_FIX

    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm or get_llm_service()

    async def fix_file(
        self,
        file_path: str,
        code: str,
        failure_output: str,
    ) -> tuple[bool, str | None, str]:
        """Ask the LLM to fix one failing test file.

        Returns (success, fixed_code | None, explanation).
        """
        prompt = render(
            "test_fix.j2",
            file_path=file_path,
            code=code,
            failure_output=failure_output,
        )

        try:
            payload = await self.llm.complete_json(prompt)
        except Exception as exc:
            logger.warning("test_fix_llm_failed", file=file_path, error=str(exc))
            return False, None, str(exc)

        if not isinstance(payload, dict):
            return False, None, "LLM response was not a dict"

        if not payload.get("changed", False):
            return False, None, payload.get("explanation", "LLM decided no fix was safe")

        fixed_code = payload.get("fixed_code", "")
        if not fixed_code or not isinstance(fixed_code, str) or fixed_code == code:
            return False, None, "No actual change in test code"

        # Validate Python syntax
        if not self._validate_syntax(fixed_code):
            return False, None, "Fixed test code has syntax errors"

        explanation = payload.get("explanation", "")
        return True, fixed_code, explanation

    @staticmethod
    def _validate_syntax(code: str) -> bool:
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False
