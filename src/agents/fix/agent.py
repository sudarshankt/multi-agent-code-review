"""FixAgent: generate fix proposals per category; commit only approved ones.

Stage A — generate_proposals():
  Called from the LangGraph apply_fixes node.
  Runs the LLM per file, validates syntax, generates a unified diff.
  Returns ProposedFix objects — no GitHub API calls.

Stage B — commit_approved():
  Called by the API endpoint POST /api/v1/reviews/{id}/fixes/apply.
  Commits only the ProposedFix entries with status=APPROVED.
  One git.commit_fixes() call per category (security → bug → style → performance).
"""

from __future__ import annotations

import ast
import difflib
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
from src.models.fix import FixStatus, ProposedFix
from src.prompts.loader import render
from src.services.git_service import GitService
from src.services.llm_service import LLMService, get_llm_service

logger = get_logger(__name__)


class FixAgent:
    name = AGENT_FIX

    def __init__(self, llm: LLMService | None = None, git: GitService | None = None) -> None:
        self.llm = llm or get_llm_service()
        self.git = git

    # ------------------------------------------------------------------
    # Stage A: Generate proposals (no GitHub API calls)
    # ------------------------------------------------------------------

    async def generate_proposals(
        self,
        files: dict[str, str],
        findings: list[Finding],
        review_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> list[ProposedFix]:
        """
        For each fixable finding, ask the LLM for a fix and wrap it as a
        ProposedFix with a unified diff. Nothing is committed to GitHub.
        """
        context = context or {}

        eligible = [f for f in findings if f.severity.value in FIXABLE_SEVERITIES]
        by_category: dict[str, list[Finding]] = {}
        for f in eligible:
            by_category.setdefault(f.category.value, []).append(f)

        all_proposals: list[ProposedFix] = []
        current_files = dict(files)

        for category in FIX_CATEGORY_ORDER:
            if category not in by_category:
                continue
            proposals, updated = await self._propose_category(
                current_files, by_category[category], category, review_id
            )
            all_proposals.extend(proposals)
            current_files = updated

        return all_proposals

    async def _propose_category(
        self,
        files: dict[str, str],
        findings: list[Finding],
        category: str,
        review_id: str,
    ) -> tuple[list[ProposedFix], dict[str, str]]:
        """Generate proposals for one category. Returns (proposals, updated_files)."""
        by_file: dict[str, list[Finding]] = {}
        for f in findings:
            by_file.setdefault(f.location.file_path, []).append(f)

        limited = list(by_file.items())[:MAX_FIX_FILES_PER_CATEGORY]
        proposals: list[ProposedFix] = []
        updated = dict(files)

        for file_path, file_findings in limited:
            if file_path not in files:
                continue

            code = files[file_path]
            fix_result, fixed_code = await self._fix_file(code, file_path, file_findings, category)

            if fix_result.success and fixed_code and fixed_code != code:
                diff = self._make_diff(code, fixed_code, file_path)
                proposal = ProposedFix(
                    review_id=review_id,
                    category=category,
                    file_path=file_path,
                    finding_ids=[f.id for f in file_findings],
                    original_code=code,
                    fixed_code=fixed_code,
                    diff=diff,
                    explanation=fix_result.commit_message or "",
                )
                proposals.append(proposal)
                # Pass fixed code to the next category as the current state
                updated[file_path] = fixed_code
            else:
                logger.info(
                    "proposal_skipped",
                    file=file_path,
                    category=category,
                    reason=fix_result.error or "no change",
                )

        return proposals, updated

    @staticmethod
    def _make_diff(original: str, fixed: str, file_path: str) -> str:
        """Generate a unified diff string between original and fixed code."""
        return "\n".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                fixed.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            )
        )

    # ------------------------------------------------------------------
    # Stage B: Commit approved proposals (calls GitHub API)
    # ------------------------------------------------------------------

    async def commit_approved(
        self,
        proposals: list[ProposedFix],
        owner: str,
        repo: str,
        branch: str,
    ) -> list[ProposedFix]:
        """
        Commit all APPROVED proposals grouped by category.
        Mutates each proposal's status and commit_sha in-place.
        Returns the same list with updated statuses.
        """
        if not self.git:
            logger.warning("commit_approved_no_git_service")
            for p in proposals:
                p.status = FixStatus.FAILED
                p.error = "No git service configured."
            return proposals

        approved = [p for p in proposals if p.status == FixStatus.APPROVED]
        if not approved:
            logger.info("commit_approved_nothing_to_commit")
            return proposals

        by_category: dict[str, list[ProposedFix]] = {}
        for p in approved:
            by_category.setdefault(p.category, []).append(p)

        for category in FIX_CATEGORY_ORDER:
            if category not in by_category:
                continue
            cat_proposals = by_category[category]
            to_commit = {p.file_path: p.fixed_code for p in cat_proposals}
            fixed_count = len(to_commit)

            try:
                msg = f"[pr-review] GENAI=YES: fix {category} issues ({fixed_count} files)"
                sha = await self.git.commit_fixes(owner, repo, branch, to_commit, msg)
                for p in cat_proposals:
                    p.status = FixStatus.COMMITTED
                    p.commit_sha = sha
                logger.info("category_committed", category=category, files=fixed_count, sha=sha)
            except GitOperationError as exc:
                logger.error("commit_failed", category=category, error=str(exc))
                for p in cat_proposals:
                    p.status = FixStatus.FAILED
                    p.error = f"Commit failed: {exc}"

        return proposals

    # ------------------------------------------------------------------
    # Legacy run() — kept for backward compatibility with existing tests
    # ------------------------------------------------------------------

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
        Original commit-immediately flow. Still used by tests.
        Generates proposals then immediately commits all of them.
        """
        if not self.git:
            logger.warning("fix_agent_no_git_service")
            return [], {}

        context = context or {}
        eligible = [f for f in findings if f.severity.value in FIXABLE_SEVERITIES]
        by_category: dict[str, list[Finding]] = {}
        for f in eligible:
            by_category.setdefault(f.category.value, []).append(f)

        all_fix_results: list[FixResult] = []
        updated_files = dict(files)

        for category in FIX_CATEGORY_ORDER:
            if category not in by_category:
                continue
            cat_results, cat_updated = await self._fix_category(
                updated_files, by_category[category], category, owner, repo, branch
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
        by_file: dict[str, list[Finding]] = {}
        for f in findings:
            by_file.setdefault(f.location.file_path, []).append(f)

        limited_files = list(by_file.items())[:MAX_FIX_FILES_PER_CATEGORY]
        fixed_count = 0
        to_commit: dict[str, str] = {}
        results: list[FixResult] = []
        updated = dict(files)

        for file_path, file_findings in limited_files:
            if file_path not in files:
                continue
            code = files[file_path]
            result, fixed_code = await self._fix_file(code, file_path, file_findings, category)
            results.append(result)

            if result.success and fixed_code:
                if file_path.endswith(PYTHON_EXTENSIONS):
                    if not self._validate_syntax(fixed_code):
                        result.success = False
                        result.error = "Fixed code has syntax errors."
                        continue
                if fixed_code == code:
                    result.success = False
                    result.error = "No actual changes in fixed code."
                    continue
                to_commit[file_path] = fixed_code
                updated[file_path] = fixed_code
                fixed_count += 1

        if to_commit and fixed_count > 0:
            try:
                msg = f"[pr-review] GENAI=YES: fix {category} issues ({fixed_count} files)"
                sha = await self.git.commit_fixes(owner, repo, branch, to_commit, msg)
                for result in results:
                    if result.success:
                        result.commit_sha = sha
                        result.commit_message = msg
                logger.info("category_committed", category=category, files=fixed_count, commit_sha=sha)
            except GitOperationError as exc:
                logger.error("commit_failed", category=category, error=str(exc))
                for result in results:
                    if result.success:
                        result.success = False
                        result.error = f"Commit failed: {exc}"

        return results, updated

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _fix_file(
        self, code: str, file_path: str, findings: list[Finding], category: str
    ) -> tuple[FixResult, str | None]:
        """Ask the LLM to fix one file. Returns (FixResult, fixed_code | None)."""
        from src.models.finding import Category as Cat

        result = FixResult(category=Cat(category), file_path=file_path)
        result.original_code = code

        try:
            prompt = render("fix.j2", category=category, file_path=file_path, code=code, findings=findings)
            payload = await self.llm.complete_json(prompt)
        except Exception as exc:
            logger.warning("llm_fix_failed", file=file_path, error=str(exc))
            result.error = str(exc)
            return result, None

        if not isinstance(payload, dict):
            result.error = "LLM response was not a dict."
            return result, None

        if not payload.get("changed", False):
            result.error = "LLM decided no fix was safe."
            return result, None

        fixed_code = payload.get("fixed_code", "")
        if not fixed_code or not isinstance(fixed_code, str):
            result.error = "LLM did not return fixed_code."
            return result, None

        # Validate Python syntax before returning
        if file_path.endswith(PYTHON_EXTENSIONS) and not self._validate_syntax(fixed_code):
            result.error = "Fixed code has syntax errors."
            return result, None

        if fixed_code == code:
            result.error = "No actual changes in fixed code."
            return result, None

        result.fixed_code = fixed_code
        result.commit_message = payload.get("explanation", "")
        result.success = True
        return result, fixed_code

    def _validate_syntax(self, code: str) -> bool:
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False
