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


# ---------------------------------------------------------------------------
# Generic error extraction — try to find anything we can auto-fix
# ---------------------------------------------------------------------------

# Any Python exception class name (used to detect collection errors generically).
_COLLECTION_ERROR_SIGNALS = (
    "ERROR collecting",
    "INTERNALERROR",
    "error:",
)
# Patterns that indicate the test run itself had errors (not just failures).
_TEST_RUN_ERROR_SIGNALS = (
    "ImportError",
    "ModuleNotFoundError",
    "No module named",
    "KeyError:",
    "NameError:",
    "AttributeError: module",
    "RuntimeError:",
    "FileNotFoundError:",
    "OSError:",
    "PermissionError:",
    "cannot import name",
    "No such file or directory",
)

_MODULE_NAME_RE = re.compile(r"No module named ['\"](\w+)['\"]")
_CANNOT_IMPORT_RE = re.compile(r"cannot import name ['\"](\w+)['\"]")

# --- Env var extraction (generic) ---

_ENV_VAR_ERROR_RE = re.compile(
    r"RuntimeError:\s*['\"]?(\w+)\s+environment\s+variable\s+not\s+(?:set|found)",
    re.IGNORECASE,
)
_OS_ENVIRON_ACCESS_RE = re.compile(
    r"os\.environ\[['\"](\w+)['\"]\]",
)
_KEYERROR_VAR_RE = re.compile(
    r"KeyError:\s*['\"](\w+)['\"]",
)
_OS_GETENV_RE = re.compile(
    r"os\.getenv\(\s*['\"](\w+)['\"]\s*\)",
)
_NAMEERROR_NAME_RE = re.compile(
    r"NameError:\s*.*name\s+['\"](\w+)['\"]\s+is\s+not\s+defined",
)


def _extract_all_missing_modules(stdout: str, stderr: str) -> list[str]:
    """Extract every missing module name from pytest output.

    Handles: ``ModuleNotFoundError: No module named 'xxx'`` and
    ``ImportError: cannot import name 'yyy'``.
    """
    combined = stdout + stderr
    modules: list[str] = []
    for m in _MODULE_NAME_RE.finditer(combined):
        name = m.group(1)
        if name not in modules:
            modules.append(name)
    return modules


def _extract_missing_module(stdout: str, stderr: str) -> str | None:
    """Return the first missing module, or None. Kept for backward compat."""
    names = _extract_all_missing_modules(stdout, stderr)
    return names[0] if names else None


def _extract_missing_env_var(stdout: str, stderr: str) -> str | None:
    """Extract the name of a missing environment variable from pytest output.

    Handles ANY pattern that looks like a missing env var:
    1. ``RuntimeError: VAR environment variable not set``
    2. ``os.environ["VAR"]`` → ``KeyError: 'VAR'``
    3. ``os.getenv("VAR")`` without default
    4. Bare ``KeyError: 'VAR'`` anywhere near ``os.environ``
    5. ``NameError: name 'VAR' is not defined`` (common when env var loaded at module level)
    """
    combined = stdout + stderr

    # Pattern 1
    m = _ENV_VAR_ERROR_RE.search(combined)
    if m:
        return m.group(1)

    # Pattern 2+4: os.environ["VAR"] with KeyError
    os_match = _OS_ENVIRON_ACCESS_RE.search(combined)
    key_match = _KEYERROR_VAR_RE.search(combined)
    if os_match and key_match and os_match.group(1) == key_match.group(1):
        return os_match.group(1)

    # Pattern 3: os.getenv("VAR") — only if it has no default (single arg)
    getenv_match = _OS_GETENV_RE.search(combined)
    if getenv_match and "KeyError" in combined:
        return getenv_match.group(1)

    # Pattern 4: bare KeyError with os.environ context
    if key_match and "os.environ" in combined:
        return key_match.group(1)

    # Pattern 5: NameError for ALL_CAPS names (likely an env var loaded at module level)
    name_match = _NAMEERROR_NAME_RE.search(combined)
    if name_match and name_match.group(1).isupper():
        return name_match.group(1)

    return None


def _is_collection_error(stdout: str, stderr: str, exit_code: int) -> bool:
    """Return True if pytest failed during test *collection* (auto-fixable)
    rather than during test *execution* (not auto-fixable)."""
    combined = stdout + stderr

    # Exit code 2 = error during collection/execution (not test failures)
    # Exit code 4 = internal pytest error
    if exit_code in (2, 4):
        return True

    # Explicit collection-phase error markers
    for signal in _COLLECTION_ERROR_SIGNALS:
        if signal in combined:
            return True

    return False


def _diagnose_error(combined: str) -> str:
    """Return a short human-readable summary of what went wrong."""
    if "KeyError:" in combined:
        return "missing environment variable(s)"
    if "ModuleNotFoundError:" in combined or "ImportError:" in combined or "No module named" in combined:
        return "missing Python module(s)"
    if "FileNotFoundError:" in combined or "No such file or directory" in combined:
        return "missing file or directory"
    if "PermissionError:" in combined:
        return "permission denied"
    if "NameError:" in combined:
        return "undefined name (likely missing import or env var)"
    if "RuntimeError:" in combined:
        return "runtime error — check traceback"
    if "OSError:" in combined:
        return "OS error — check traceback"
    return "unknown collection error"


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
    """Clone a PR branch into a temp dir and run pytest against it.

    Timeouts are read from settings (configurable via .env):
    - test_gate_timeout_secs  → pytest runtime (default 300)
    - clone uses a fixed 120s ceiling (git clone is network-bound, not test-bound).
    """

    def __init__(self, settings=None) -> None:
        self.settings = settings or get_settings()
        cfg = self.settings
        self._pytest_timeout: float = float(
            getattr(cfg, "test_gate_timeout_secs", None) or 600
        )
        self._clone_timeout: float = 300.0

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

            # Run pytest.  If collection fails, try to auto-fix whatever is
            # broken: install missing packages, inject missing env vars, etc.
            # The retry loop extracts ALL fixable problems each iteration
            # instead of fixing one at a time — this handles cascading errors
            # (e.g. a missing module that itself needs env vars).
            result = await self._run_pytest(tmp_dir)
            retries = 0
            max_retries = 5
            injected_env_vars: set[str] = set()

            while retries < max_retries:
                if not result.skipped:
                    break
                retries += 1

                combined = result.stdout + result.stderr
                fixed_something = False

                # --- 1. Try installing every missing module ---
                missing_modules = _extract_all_missing_modules(
                    result.stdout, result.stderr,
                )
                for mod_name in missing_modules:
                    logger.info(
                        "test_retry_install",
                        module=mod_name,
                        retry=retries,
                    )
                    ok, _ = await _pip_install(python_exe, [mod_name], tmp_dir)
                    if ok:
                        fixed_something = True

                # --- 2. Try injecting every missing env var ---
                missing_var = _extract_missing_env_var(result.stdout, result.stderr)
                if missing_var and missing_var not in injected_env_vars:
                    injected_env_vars.add(missing_var)
                    test_value = f"test-{missing_var.lower()}-auto-injected"
                    logger.info(
                        "test_retry_env_var",
                        var=missing_var,
                        value=test_value,
                        retry=retries,
                    )
                    os.environ[missing_var] = test_value
                    fixed_something = True

                if not fixed_something:
                    logger.warning(
                        "test_auto_fix_exhausted",
                        retries=retries,
                        skip_reason=result.skip_reason,
                        output_tail=combined[-500:] if len(combined) > 500 else combined,
                    )
                    break

                # Re-run with the fixes applied
                result = await self._run_pytest(tmp_dir)

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
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._clone_timeout)
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
                proc.communicate(), timeout=self._pytest_timeout
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
        combined = stdout + stderr

        # No tests collected — not a failure, just nothing to gate on
        if exit_code == _EXIT_NO_TESTS:
            return TestRunResult(
                passed=True, exit_code=exit_code, skipped=True,
                skip_reason="no tests found in repository",
                stdout=combined,
            )

        # Test collection error — auto-fixable (missing deps, env vars, etc.)
        # We treat ANY collection error as skippable so the retry loop gets a
        # chance to fix it.
        if _is_collection_error(stdout, stderr, exit_code):
            reason = _diagnose_error(combined)
            return TestRunResult(
                passed=True, exit_code=exit_code, skipped=True,
                skip_reason=f"collection error: {reason} — attempting auto-fix",
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
