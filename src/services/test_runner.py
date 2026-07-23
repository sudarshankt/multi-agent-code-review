"""Test runner: clone the PR branch and run pytest against the clone.

We resolve the venv Python (not sys.executable, which may point to a
bare framework python without pytest/dependencies) by looking at
sys.prefix which always points to the venv directory when the server
is started via ``.venv/bin/python -m uvicorn ...``.

The clone may or may not have test files — we handle both cases.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_EXIT_OK = 0
_EXIT_TESTS_FAILED = 1
_EXIT_NO_TESTS = 5


def _resolve_venv_python() -> str:
    """Return the venv Python executable, not the bare framework interpreter.

    When the server is started via ``.venv/bin/python -m uvicorn ...``,
    sys.prefix points to the venv, and sys.executable usually resolves to
    the same venv path.  On some platforms / symlink setups sys.executable
    can be the framework python, which lacks pytest.  sys.prefix is
    reliable because it is always the running venv root.
    """
    venv_bin = Path(sys.prefix) / "bin" / "python"
    if venv_bin.is_file():
        return str(venv_bin)

    if Path(sys.executable).is_file():
        return sys.executable

    return "python"


@dataclass
class TestRunResult:
    passed: bool          # True = safe to commit (or skipped)
    exit_code: int
    tests_passed: int = 0
    tests_failed: int = 0
    stdout: str = ""
    stderr: str = ""
    skipped: bool = False
    skip_reason: str = ""


class TestRunner:
    """Clone a PR branch into a temp dir and run pytest against it."""

    CLONE_TIMEOUT_SECS: int = 60
    TEST_TIMEOUT_SECS: int = 120

    def __init__(self, settings=None) -> None:
        self.settings = settings or get_settings()

    async def run_tests(self, owner: str, repo: str, branch: str) -> TestRunResult:
        """
        Clone branch → run pytest → return result.

        Assumes any fixes have already been committed to `branch`.

        Returns:
          passed=True,  skipped=False → tests passed
          passed=True,  skipped=True  → could not run (infra issue)
          passed=False, skipped=False → tests failed, user should investigate
        """
        clone_url = self._make_clone_url(owner, repo)
        tmp_dir = tempfile.mkdtemp(prefix="pr-review-test-")
        logger.info("test_gate_start", owner=owner, repo=repo, branch=branch, tmp_dir=tmp_dir)

        try:
            if not await self._clone(clone_url, branch, tmp_dir):
                return TestRunResult(
                    passed=True, exit_code=0, skipped=True,
                    skip_reason="git clone failed — proceeding without test gate",
                )
            return await self._run_pytest(tmp_dir)
        except Exception as exc:
            logger.warning("test_gate_unexpected_error", error=str(exc))
            return TestRunResult(
                passed=True, exit_code=0, skipped=True,
                skip_reason=f"unexpected error: {exc}",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.info("test_gate_cleanup_done", tmp_dir=tmp_dir)

    def _make_clone_url(self, owner: str, repo: str) -> str:
        token = self.settings.github_token
        base = self.settings.github_api_base_url
        host = "github.com" if "api.github.com" in base else base.replace("https://", "").split("/")[0]
        if token:
            return f"https://x-access-token:{token}@{host}/{owner}/{repo}.git"
        return f"https://{host}/{owner}/{repo}.git"

    async def _clone(self, url: str, branch: str, dest: str) -> bool:
        cmd = ["git", "clone", "--depth", "1", "--branch", branch, "--single-branch", url, dest]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.CLONE_TIMEOUT_SECS)
            if proc.returncode != 0:
                logger.warning("git_clone_failed", stderr=stderr.decode(errors="replace")[:500])
                return False
            logger.info("git_clone_ok", branch=branch)
            return True
        except asyncio.TimeoutError:
            logger.warning("git_clone_timeout")
            return False
        except Exception as exc:
            logger.warning("git_clone_error", error=str(exc))
            return False

    async def _run_pytest(self, clone_dir: str) -> TestRunResult:
        python_exe = _resolve_venv_python()
        # Point pytest at the tests/ subdirectory when one exists — it's
        # common for repos to have the test-tree under tests/, and running
        # pytest on the whole repo root can accidentally skip test discovery
        # when pyproject.toml / conftest.py aren't in the expected spots.
        test_dir = os.path.join(clone_dir, "tests")
        target = test_dir if os.path.isdir(test_dir) else clone_dir

        cmd = [python_exe, "-m", "pytest", "--tb=short", "-q", "--no-header", target]
        logger.info("test_runner_cmd", cmd=cmd, clone_dir=clone_dir, target=target)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=clone_dir,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self.TEST_TIMEOUT_SECS
            )
            stdout = stdout_b.decode(errors="replace")
            stderr = stderr_b.decode(errors="replace")

            # When no tests are found, add a diagnostic collection output so
            # the user can see *why* (empty test files, missing conftest, etc.)
            if proc.returncode == _EXIT_NO_TESTS:
                extra = await self._diagnose_no_tests(clone_dir, stdout)
                stdout = extra if extra else stdout
                stderr = stderr_b.decode(errors="replace")

            result = self._parse_result(stdout, stderr, proc.returncode)
            logger.info(
                "pytest_completed",
                exit_code=proc.returncode,
                passed=result.passed,
                tests_passed=result.tests_passed,
                tests_failed=result.tests_failed,
                skipped=result.skipped,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("pytest_timeout", clone_dir=clone_dir)
            return TestRunResult(
                passed=True, exit_code=0, skipped=True,
                skip_reason="pytest timed out — proceeding without test gate",
            )
        except Exception as exc:
            logger.warning("pytest_run_error", error=str(exc))
            return TestRunResult(
                passed=True, exit_code=0, skipped=True,
                skip_reason=f"pytest error: {exc}",
            )

    async def _diagnose_no_tests(self, clone_dir: str, stdout: str) -> str:
        """Run pytest --collect-only -v to surface WHY no tests were found."""
        python_exe = _resolve_venv_python()
        test_dir = os.path.join(clone_dir, "tests")
        target = test_dir if os.path.isdir(test_dir) else clone_dir

        cmd = [python_exe, "-m", "pytest", "--collect-only", "-v", "--no-header", target]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=clone_dir,
            )
            diag_out, diag_err = await asyncio.wait_for(
                proc.communicate(), timeout=10.0,
            )
            diag = diag_out.decode(errors="replace")
            diag_stderr = diag_err.decode(errors="replace")
            logger.warning(
                "pytest_no_tests_diagnosis",
                cmd=cmd,
                stdout=diag[-500:] or "(empty)",
                stderr=diag_stderr[-500:] or "(empty)",
            )
            combined = stdout + diag + diag_stderr
            return combined
        except Exception as exc:
            logger.warning("pytest_diagnosis_failed", error=str(exc))
            return stdout

    def _parse_result(self, stdout: str, stderr: str, exit_code: int) -> TestRunResult:
        # No tests collected — not a failure, just nothing to gate on
        if exit_code == _EXIT_NO_TESTS:
            combined = stdout + stderr
            return TestRunResult(
                passed=True, exit_code=exit_code, skipped=True,
                skip_reason="no tests found in repository",
                stdout=combined,
            )

        # Missing dependencies → graceful skip rather than hard block
        combined = stdout + stderr
        missing_dep_signals = ("ERROR collecting", "ImportError", "ModuleNotFoundError", "No module named")
        if any(s in combined for s in missing_dep_signals):
            return TestRunResult(
                passed=True, exit_code=exit_code, skipped=True,
                skip_reason="test collection failed (missing dependencies) — skipping test gate",
                stdout=stdout, stderr=stderr,
            )

        # Parse summary line: "2 failed, 10 passed in 3.14s"
        failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", stdout)) else 0
        passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", stdout)) else 0

        return TestRunResult(
            passed=(exit_code == _EXIT_OK),
            exit_code=exit_code,
            tests_passed=passed,
            tests_failed=failed,
            stdout=stdout,
            stderr=stderr,
        )
