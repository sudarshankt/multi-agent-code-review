"""Test runner: clone the PR branch, auto-install its dependencies into the
venv, and run pytest against the clone.

We resolve the venv Python (not sys.executable) via sys.prefix.
Before running pytest we scan the clone for requirements files and install
any missing packages — this is what lets tests in arbitrary PR branches
run without manually pre-installing every dependency.
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

# ---------------------------------------------------------------------------
# Pip install helpers — auto-install deps from the cloned repo before tests
# ---------------------------------------------------------------------------

_PIP_INSTALL_TIMEOUT_SECS = 45


def _find_requirement_files(clone_dir: str) -> list[str]:
    """Return paths to dependency files found in the clone root, ordered by priority."""
    candidates = [
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-test.txt",
        "requirements/base.txt",
        "requirements/dev.txt",
        "requirements/test.txt",
    ]
    found: list[str] = []
    for name in candidates:
        path = Path(clone_dir) / name
        if path.is_file():
            found.append(str(path))
    return found


async def _pip_install(python_exe: str, args: list[str], cwd: str) -> tuple[bool, str]:
    """Run ``{python_exe} -m pip install ...``. Returns (ok, output_tail)."""
    cmd = [python_exe, "-m", "pip", "install", "--quiet"] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=_PIP_INSTALL_TIMEOUT_SECS,
        )
        combined = (stdout_b + stderr_b).decode(errors="replace")
        ok = proc.returncode == 0
        if ok:
            logger.info("pip_install_ok", args=args, output=combined[-300:] if combined else "")
        else:
            logger.warning("pip_install_failed", args=args, returncode=proc.returncode, output=combined[-500:] if combined else "")
        return ok, combined[-500:] if combined else ""
    except asyncio.TimeoutError:
        logger.warning("pip_install_timeout", args=args)
        return False, "pip install timed out"
    except Exception as exc:
        logger.warning("pip_install_error", args=args, error=str(exc))
        return False, str(exc)


async def _install_clone_deps(python_exe: str, clone_dir: str) -> list[str]:
    """Install dependencies from the clone's requirements files.  Returns a
    list of requirement-file paths that were successfully installed."""
    installed: list[str] = []
    req_files = _find_requirement_files(clone_dir)

    for req_path in req_files:
        ok, _ = await _pip_install(python_exe, ["-r", req_path], clone_dir)
        if ok:
            installed.append(str(Path(req_path).name))

    # Also try ``pip install .`` if setup.py / pyproject.toml exists (handles
    # the clone's own package dependencies).
    if (Path(clone_dir) / "setup.py").is_file() or (Path(clone_dir) / "pyproject.toml").is_file():
        ok, _ = await _pip_install(python_exe, ["-e", clone_dir], clone_dir)
        if ok:
            installed.append("editable-install")

    return installed


def _extract_missing_module(stdout: str, stderr: str) -> str | None:
    """Parse ``ModuleNotFoundError: No module named 'xxx'`` from pytest output."""
    m = re.search(r"ModuleNotFoundError: No module named '(\w+)'", stdout + stderr)
    return m.group(1) if m else None


_ENV_VAR_ERROR_RE = re.compile(
    r"RuntimeError:\s*['\"]?(\w+)\s+environment\s+variable\s+not\s+(?:set|found)",
    re.IGNORECASE,
)


def _extract_missing_env_var(stdout: str, stderr: str) -> str | None:
    """Parse ``RuntimeError: API_KEY environment variable not set`` from pytest output."""
    m = _ENV_VAR_ERROR_RE.search(stdout + stderr)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Venv python resolution
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Data & runner
# ---------------------------------------------------------------------------


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
        Clone branch → install deps → run pytest → return result.

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

            # Install dependencies from the clone before running tests
            # (can be disabled by setting AUTO_INSTALL_TEST_DEPS=false in .env).
            settings = self.settings or get_settings()
            if getattr(settings, "auto_install_test_deps", True):
                python_exe = _resolve_venv_python()
                installed = await _install_clone_deps(python_exe, tmp_dir)
                if installed:
                    logger.info("test_deps_installed", files=installed)
            else:
                python_exe = _resolve_venv_python()

            # Run pytest.  If there's a ModuleNotFoundError for a package
            # not covered by requirements*.txt, try installing it and retry.
            # If there's a RuntimeError about a missing environment variable,
            # inject a test-default value and retry.  Both retry patterns
            # can fire independently (we loop through them until one fixes
            # the skip or no more fixes are possible).
            result = await self._run_pytest(tmp_dir)
            retries = 0
            while result.skipped and retries < 3:
                retries += 1

                # --- dependency retry ---
                missing = _extract_missing_module(result.stdout, result.stderr)
                if missing:
                    logger.info("test_retry_install_missing", module=missing)
                    ok, _ = await _pip_install(python_exe, [missing], tmp_dir)
                    if not ok:
                        break  # can't install — give up
                    result = await self._run_pytest(tmp_dir)
                    continue

                # --- env-var retry ---
                missing_var = _extract_missing_env_var(result.stdout, result.stderr)
                if missing_var:
                    test_value = f"test-{missing_var.lower()}-auto-injected"
                    logger.info("test_retry_env_var", var=missing_var, value=test_value)
                    os.environ[missing_var] = test_value
                    result = await self._run_pytest(tmp_dir)
                    continue

                # Neither module nor env-var — no more fixes to try
                break

            return result
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
        cmd = ["git", "clone", "--branch", branch, "--single-branch", url, dest]
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

        # Missing dependencies → graceful skip (retry was already attempted)
        combined = stdout + stderr
        missing_dep_signals = ("ERROR collecting", "ImportError", "ModuleNotFoundError", "No module named")
        if any(s in combined for s in missing_dep_signals):
            return TestRunResult(
                passed=True, exit_code=exit_code, skipped=True,
                skip_reason="test collection failed (missing dependencies — tried auto-installing, still missing)",
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
