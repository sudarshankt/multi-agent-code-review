"""FixAgent: auto-fix critical/high/medium findings, commit per category."""

from __future__ import annotations

import ast
from typing import Any

from src.core.constants import (
    AGENT_FIX,
    FIXABLE_SEVERITIES,
    FIX_CATEGORY_ORDER,
    MAX_FIX_FILES_PER_CATEGORY,
    PYTHON_EXTENSIONS,
)
from src.core.exceptions import GitOperationError
from src.core.logging import get_logger
from src.models.finding import Finding, FixResult
from src.prompts.loader import render
from src.services.git_service import GitService
from src.services.llm_service import LLMService, get_llm_service

logger = get_logger(__name__)


class FixAgent:
    name = AGENT_FIX

    def __init__(self, llm: LLMService | None = None, git: GitService | None = None) -> None:
        self.llm = llm or get_llm_service()
        self.git = git

    async def run(
        self,
        files: dict[str, str],
        findings: list[Finding],
        owner: str,
        repo: str,
        branch: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[list[FixResult], dict[str, str]]:
        """
        Fix findings and commit per category. Return (fix_results, updated_files).
        updated_files are those that were successfully fixed, for next-category
        processing.
        """
        if not self.git:
            logger.warning("fix_agent_no_git_service")
            return [], {}

        context = context or {}

        # Filter: only critical/high/medium (bug #8), group by category (bug #7).
        eligible = [
            f for f in findings if f.severity.value in FIXABLE_SEVERITIES
        ]
        by_category: dict[str, list[Finding]] = {}
        for f in eligible:
            by_category.setdefault(f.category.value, []).append(f)

        all_fix_results: list[FixResult] = []
        updated_files = dict(files)

        # Process categories in order (bug #4 — GENAI=YES in message).
        for category in FIX_CATEGORY_ORDER:
            if category not in by_category:
                continue

            cat_findings = by_category[category]
            cat_results, cat_updated = await self._fix_category(
                updated_files, cat_findings, category, owner, repo, branch
            )
            all_fix_results.extend(cat_results)
            updated_files = cat_updated

        return all_fix_results, updated_files

    async def _fix_category(
        self,
        files: dict[str, str],
        findings: list[Finding],
        category: str,
        owner: str,
        repo: str,
        branch: str,
    ) -> tuple[list[FixResult], dict[str, str]]:
        """Fix one category's findings, commit, return (results, updated files)."""
        by_file: dict[str, list[Finding]] = {}
        for f in findings:
            by_file.setdefault(f.location.file_path, []).append(f)

        # Limit to MAX_FIX_FILES_PER_CATEGORY (bug #9).
        limited_files = list(by_file.items())[: MAX_FIX_FILES_PER_CATEGORY]
        fixed_count = 0
        to_commit: dict[str, str] = {}
        results: list[FixResult] = []
        updated = dict(files)

        for file_path, file_findings in limited_files:
            if file_path not in files:
                continue

            code = files[file_path]
            result, fixed_code = await self._fix_file(
                code, file_path, file_findings, category
            )
            results.append(result)

            if result.success and fixed_code:
                # Validate syntax for Python files (bug #3 — compile check).
                if file_path.endswith(PYTHON_EXTENSIONS):
                    if not self._validate_syntax(fixed_code):
                        result.success = False
                        result.error = "Fixed code has syntax errors."
                        continue

                # Verify content actually changed (don't commit unchanged code)
                if fixed_code == code:
                    result.success = False
                    result.error = "No actual changes in fixed code."
                    continue

                to_commit[file_path] = fixed_code
                updated[file_path] = fixed_code
                fixed_count += 1

        # Commit the fixed files per category.
        if to_commit and fixed_count > 0:
            try:
                msg = f"[pr-review] GENAI=YES: fix {category} issues ({fixed_count} files)"
                sha = await self.git.commit_fixes(owner, repo, branch, to_commit, msg)
                for result in results:
                    if result.success:
                        result.commit_sha = sha
                        result.commit_message = msg
                logger.info(
                    "category_committed",
                    category=category,
                    files=fixed_count,
                    commit_sha=sha,
                )
            except GitOperationError as exc:
                logger.error("commit_failed", category=category, error=str(exc))
                for result in results:
                    if result.success:
                        result.success = False
                        result.error = f"Commit failed: {exc}"
        elif findings:
            logger.info(
                "category_skipped_no_fixes",
                category=category,
                findings_count=len(findings),
                fixable_count=fixed_count,
            )

        return results, updated

    async def _fix_file(
        self, code: str, file_path: str, findings: list[Finding], category: str
    ) -> tuple[FixResult, str | None]:
        """Ask the LLM to fix one file's findings. Return (result, fixed_code)."""
        result = FixResult(category=category, file_path=file_path)
        result.original_code = code

        try:
            prompt = render(
                "fix.j2",
                category=category,
                file_path=file_path,
                code=code,
                findings=findings,
            )
            payload = await self.llm.complete_json(prompt)
        except Exception as exc:  # noqa: BLE001 - per-file try/except (bug #9)
            logger.warning("llm_fix_failed", file=file_path, error=str(exc))
            result.error = str(exc)
            return result, None

        if not isinstance(payload, dict):
            result.error = "LLM response was not a dict."
            return result, None

        changed = payload.get("changed", False)
        if not changed:
            result.error = "LLM decided no fix was safe."
            return result, None

        fixed_code = payload.get("fixed_code", "")
        if not fixed_code or not isinstance(fixed_code, str):
            result.error = "LLM did not return fixed_code."
            return result, None

        result.fixed_code = fixed_code
        result.success = True
        return result, fixed_code

    def _validate_syntax(self, code: str) -> bool:
        """Check Python syntax using compile()."""
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False
