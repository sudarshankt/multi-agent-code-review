"""Fix review endpoints — approve/reject proposals, apply approved fixes, run tests,
and auto-fix failing tests via LLM in a retry loop."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.logging import get_logger
from src.models.fix import FixStatus, TestRunStatus, TestRunSummary

logger = get_logger(__name__)

router = APIRouter()

_MAX_TEST_FIX_RETRIES = 3


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ReviewFixAction(BaseModel):
    action: str  # "approve" | "reject"


class ApplyFixesResponse(BaseModel):
    committed: int
    failed: int
    commit_shas: dict[str, str]  # {category: sha}


class RunTestsRequest(BaseModel):
    fix_ids: list[str] = []  # unused now that tests run against the whole committed branch


# ---------------------------------------------------------------------------
# Helper: look up a review from the in-memory store
# ---------------------------------------------------------------------------

def _get_review(review_id: str):
    from src.api.endpoints.review import _reviews
    review = _reviews.get(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


# ---------------------------------------------------------------------------
# GET /reviews/{id}/fixes  — list proposed fixes with diffs
# ---------------------------------------------------------------------------

@router.get("/reviews/{review_id}/fixes")
async def list_proposed_fixes(review_id: str) -> dict[str, Any]:
    review = _get_review(review_id)
    return {
        "review_id": review_id,
        "proposed_fixes": [p.model_dump() for p in review.proposed_fixes],
        "total": len(review.proposed_fixes),
        "pending": review.pending_fix_count,
        "approved": review.approved_fix_count,
        "committed": review.committed_fix_count,
    }


# ---------------------------------------------------------------------------
# PATCH /reviews/{id}/fixes/{fix_id}  — approve or reject one fix
# ---------------------------------------------------------------------------

@router.patch("/reviews/{review_id}/fixes/{fix_id}")
async def review_fix(review_id: str, fix_id: str, body: ReviewFixAction) -> dict[str, Any]:
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    review = _get_review(review_id)
    proposal = next((p for p in review.proposed_fixes if p.id == fix_id), None)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposed fix not found")

    if proposal.status in (FixStatus.COMMITTED, FixStatus.FAILED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change status of a {proposal.status.value} fix",
        )

    old_status = proposal.status
    proposal.status = FixStatus.APPROVED if body.action == "approve" else FixStatus.REJECTED

    # Publish SSE notification
    from src.api.endpoints.sse import publish_event
    await publish_event(
        review_id,
        "fix_status_changed",
        {"fix_id": fix_id, "old_status": old_status.value, "new_status": proposal.status.value},
    )

    logger.info("fix_reviewed", review_id=review_id, fix_id=fix_id, action=body.action)
    return {"fix_id": fix_id, "status": proposal.status.value}


# ---------------------------------------------------------------------------
# POST /reviews/{id}/fixes/apply  — commit all approved fixes to GitHub
# ---------------------------------------------------------------------------

@router.post("/reviews/{review_id}/fixes/apply")
async def apply_approved_fixes(review_id: str) -> ApplyFixesResponse:
    review = _get_review(review_id)

    approved = [p for p in review.proposed_fixes if p.status == FixStatus.APPROVED]
    if not approved:
        raise HTTPException(status_code=400, detail="No approved fixes to apply")

    pr = review.pr_info
    branch = pr.head_branch or "main"

    from src.agents.fix.agent import FixAgent
    from src.services.git_service import GitService

    commit_shas: dict[str, str] = {}
    committed = 0
    failed = 0

    async with GitService() as git:
        agent = FixAgent(git=git)
        await agent.commit_approved(approved, pr.owner, pr.repo, branch)

    for p in approved:
        if p.status == FixStatus.COMMITTED:
            committed += 1
            if p.commit_sha:
                commit_shas[p.category] = p.commit_sha
        else:
            failed += 1

    review.total_fixes = committed
    if committed > 0 and review.pr_info.html_url:
        review.fix_pr_url = review.pr_info.html_url

    from src.api.endpoints.sse import publish_event
    await publish_event(
        review_id,
        "fixes_committed",
        {
            "committed_count": committed,
            "failed_count": failed,
            "commit_shas": commit_shas,
        },
    )

    logger.info("fixes_applied", review_id=review_id, committed=committed, failed=failed)
    return ApplyFixesResponse(committed=committed, failed=failed, commit_shas=commit_shas)


# ---------------------------------------------------------------------------
# POST /reviews/{id}/fixes/run-tests  — trigger optional post-commit test run
#
# Tests run AFTER fixes are committed (not before). By the time this endpoint
# is callable, the approved fixes are already on the PR branch, so we simply
# clone the branch as-is and run pytest — no need to overlay uncommitted
# code onto the clone.
# ---------------------------------------------------------------------------

@router.post("/reviews/{review_id}/fixes/run-tests", status_code=202)
async def run_tests(review_id: str, body: RunTestsRequest) -> dict[str, Any]:
    review = _get_review(review_id)

    committed = [p for p in review.proposed_fixes if p.status == FixStatus.COMMITTED]
    if not committed:
        raise HTTPException(
            status_code=400,
            detail="No committed fixes to test. Apply approved fixes first.",
        )

    asyncio.create_task(_run_test_gate(review_id))
    return {"status": "running", "message": "Test run started. Watch SSE for updates."}


async def _run_test_gate(review_id: str) -> None:
    from src.api.endpoints.review import _reviews
    from src.api.endpoints.sse import publish_event
    from src.services.test_runner import TestRunner

    review = _reviews.get(review_id)
    if not review:
        return

    # Publish "running" status immediately
    await publish_event(
        review_id,
        "test_run_update",
        {"status": TestRunStatus.RUNNING.value, "tests_passed": 0, "tests_failed": 0},
    )

    pr = review.pr_info

    started = time.monotonic()
    runner = TestRunner()
    result = await runner.run_tests(pr.owner, pr.repo, pr.head_branch or "main")
    duration = round(time.monotonic() - started, 2)

    summary = TestRunSummary(
        status=TestRunStatus.SKIPPED if result.skipped else (
            TestRunStatus.PASSED if result.passed else TestRunStatus.FAILED
        ),
        tests_passed=result.tests_passed,
        tests_failed=result.tests_failed,
        skipped=result.skipped,
        skip_reason=result.skip_reason,
        output=result.stdout[-2000:] if result.stdout else "",
        duration_seconds=duration,
    )
    review.test_run = summary

    await publish_event(
        review_id,
        "test_run_update",
        {
            "status": summary.status.value,
            "tests_passed": summary.tests_passed,
            "tests_failed": summary.tests_failed,
            "skipped": summary.skipped,
            "skip_reason": summary.skip_reason,
            "output_tail": summary.output,
            "duration_seconds": duration,
        },
    )
    logger.info("test_gate_complete", review_id=review_id, status=summary.status.value)


# ---------------------------------------------------------------------------
# POST /reviews/{id}/fixes/fix-tests  — auto-fix failing tests in a loop
# ---------------------------------------------------------------------------


class FixTestsResponse(BaseModel):
    status: str  # "fixed" | "failed" | "no_failures"
    iterations: int
    tests_passed: int = 0
    tests_failed: int = 0
    message: str = ""


@router.post("/reviews/{review_id}/fixes/fix-tests", status_code=202)
async def fix_failing_tests(review_id: str) -> dict[str, Any]:
    review = _get_review(review_id)

    if not review.test_run or review.test_run.status != TestRunStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail="No failing test results found. Run tests first.",
        )

    committed = [p for p in review.proposed_fixes if p.status == FixStatus.COMMITTED]
    if not committed:
        raise HTTPException(
            status_code=400,
            detail="No committed fixes found. Apply approved fixes and run tests first.",
        )

    asyncio.create_task(_run_test_fix_loop(review_id))
    return {"status": "running", "message": "Test-fixing loop started. Watch SSE for updates."}


async def _run_test_fix_loop(review_id: str) -> None:
    """Core loop: run tests → fix failures → commit → re-run until all pass."""
    from src.agents.test_fix.agent import TestFixAgent, parse_failing_files
    from src.api.endpoints.review import _reviews
    from src.api.endpoints.sse import publish_event
    from src.services.git_service import GitService
    from src.services.test_runner import TestRunner

    review = _reviews.get(review_id)
    if not review:
        return

    pr = review.pr_info
    branch = pr.head_branch or "main"
    settings = review.pr_info  # not needed; use config directly
    runner = TestRunner()
    agent = TestFixAgent()
    iteration = 0
    result = None

    # Initial test data from the stored test_run
    last_output = review.test_run.output if review.test_run else ""

    while iteration < _MAX_TEST_FIX_RETRIES:
        iteration += 1
        await publish_event(
            review_id, "test_fix_iteration",
            {"iteration": iteration, "max": _MAX_TEST_FIX_RETRIES, "status": "running_tests"},
        )

        # 1. Run tests against the branch (already has previous fixes)
        result = await runner.run_tests(pr.owner, pr.repo, branch)
        last_output = result.stdout

        # Build summary & store on review
        summary = TestRunSummary(
            status=TestRunStatus.SKIPPED if result.skipped else (
                TestRunStatus.PASSED if result.passed else TestRunStatus.FAILED
            ),
            tests_passed=result.tests_passed,
            tests_failed=result.tests_failed,
            skipped=result.skipped,
            skip_reason=result.skip_reason,
            output=result.stdout[-2000:] if result.stdout else "",
            duration_seconds=0,
        )
        review.test_run = summary
        await publish_event(
            review_id, "test_run_update",
            {
                "status": summary.status.value,
                "tests_passed": summary.tests_passed,
                "tests_failed": summary.tests_failed,
                "skipped": summary.skipped,
                "skip_reason": summary.skip_reason,
                "output_tail": summary.output,
                "iteration": iteration,
            },
        )

        # 2. All pass → done
        if result.passed and not result.skipped:
            await publish_event(
                review_id, "test_fix_complete",
                {"status": "all_passed", "iterations": iteration, "message": f"All {result.tests_passed} tests pass after {iteration} iteration(s)."},
            )
            logger.info("test_fix_all_pass", review_id=review_id, iterations=iteration)
            return

        # 3. No failures to fix (skipped, no tests, etc.)
        failing = parse_failing_files(result.stdout)
        if not failing:
            await publish_event(
                review_id, "test_fix_complete",
                {"status": "cannot_fix", "iterations": iteration, "message": result.skip_reason or "No failing test files to fix"},
            )
            logger.info("test_fix_cannot_fix", review_id=review_id, reason=result.skip_reason)
            return

        # 4. Clone branch and read failing test files
        await publish_event(
            review_id, "test_fix_iteration",
            {"iteration": iteration, "max": _MAX_TEST_FIX_RETRIES, "status": "fixing", "files": list(failing.keys())},
        )

        fixed_files, to_commit_files = {}, {}
        tmp_dir = await _clone_review_branch(pr.owner, pr.repo, branch)
        if not tmp_dir:
            logger.warning("test_fix_clone_failed", review_id=review_id)
            break

        try:
            for file_path in failing.keys():
                await publish_event(
                    review_id, "test_fix_file",
                    {"iteration": iteration, "file_path": file_path, "status": "fixing"},
                )

                code = _read_clone_file(tmp_dir, file_path)
                # If the exact path doesn't resolve, try some fallbacks
                # (e.g. the test tree might be at the repo root instead of
                # tests/).  We try a few common layouts before giving up.
                if code is None:
                    alt_paths = [
                        file_path.removeprefix("tests/"),
                        f"tests/{Path(file_path).name}",
                        f"test/{Path(file_path).name}",
                    ]
                    for alt in alt_paths:
                        if alt == file_path:
                            continue
                        code = _read_clone_file(tmp_dir, alt)
                        if code is not None:
                            file_path = alt  # use the found path
                            break

                if code is None:
                    logger.warning("test_fix_file_not_found", file_path=file_path)
                    await publish_event(
                        review_id, "test_fix_file",
                        {"iteration": iteration, "file_path": file_path, "status": "skipped", "reason": "file not found in clone"},
                    )
                    continue

                success, fixed_code, explanation = await agent.fix_file(
                    file_path, code, failing[file_path],
                )

                await publish_event(
                    review_id, "test_fix_file",
                    {
                        "iteration": iteration, "file_path": file_path,
                        "status": "fixed" if success else "skipped",
                        "explanation": explanation if success else f"skipped: {explanation}",
                    },
                )

                if success and fixed_code and fixed_code != code:
                    to_commit_files[file_path] = fixed_code
                    logger.info(
                        "test_fix_file_fixed", iteration=iteration, file_path=file_path, explanation=explanation,
                    )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # 5. Commit all fixes from this iteration
        if to_commit_files:
            try:
                msg = f"[pr-review] GENAI=YES: fix {len(to_commit_files)} failing test(s) — iteration {iteration}"
                async with GitService() as git:
                    sha = await git.commit_fixes(pr.owner, pr.repo, branch, to_commit_files, msg)
                await publish_event(
                    review_id, "test_fix_committed",
                    {"iteration": iteration, "files": len(to_commit_files), "commit_sha": sha},
                )
                logger.info("test_fix_committed", iteration=iteration, files=len(to_commit_files), sha=sha)
            except Exception as exc:
                logger.error("test_fix_commit_failed", iteration=iteration, error=str(exc))
                break
        else:
            # No fixes produced this iteration → cannot make progress
            await publish_event(
                review_id, "test_fix_complete",
                {"status": "no_progress", "iterations": iteration, "message": "LLM could not fix remaining failures. Manual review needed."},
            )
            logger.info("test_fix_no_progress", review_id=review_id, iteration=iteration)
            break

    # Max retries reached
    final_status = "all_passed" if (result and result.passed and not result.skipped) else "max_retries"
    await publish_event(
        review_id, "test_fix_complete",
        {
            "status": final_status,
            "iterations": iteration,
            "tests_passed": result.tests_passed if result else 0,
            "tests_failed": result.tests_failed if result else 0,
            "message": f"Test-fix loop complete: {final_status} after {iteration} iteration(s)",
        },
    )
    logger.info("test_fix_loop_done", review_id=review_id, iteration=iteration, status=final_status)


# ---------------------------------------------------------------------------
# Helpers for the test-fixing loop
# ---------------------------------------------------------------------------

async def _clone_review_branch(owner: str, repo: str, branch: str) -> str | None:
    """Shallow-clone a PR branch to a temp dir. Returns the dir path or None."""
    from src.core.config import get_settings

    settings = get_settings()
    token = settings.github_token
    base = settings.github_api_base_url
    host = "github.com" if "api.github.com" in base else base.replace("https://", "").split("/")[0]
    url = f"https://x-access-token:{token}@{host}/{owner}/{repo}.git" if token else f"https://{host}/{owner}/{repo}.git"

    tmp_dir = tempfile.mkdtemp(prefix="pr-review-fix-")

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--branch", branch, "--single-branch", url, tmp_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            logger.warning("test_fix_clone_failed_log", stderr=stderr.decode(errors="replace")[:500])
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None
        return tmp_dir
    except asyncio.TimeoutError:
        logger.warning("test_fix_clone_timeout")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None
    except Exception as exc:
        logger.warning("test_fix_clone_error_log", error=str(exc))
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None


def _read_clone_file(clone_dir: str, file_path: str) -> str | None:
    """Read a file from the cloned repo. Returns content or None."""
    target = Path(clone_dir) / file_path
    if not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("test_fix_read_error", file=file_path, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# GET /reviews/{id}/fixes/test-results  — retrieve test run summary
# ---------------------------------------------------------------------------

@router.get("/reviews/{review_id}/fixes/test-results")
async def get_test_results(review_id: str) -> dict[str, Any]:
    review = _get_review(review_id)
    if not review.test_run:
        return {"status": "not_run", "message": "No test run has been triggered for this review"}
    return review.test_run.model_dump()
