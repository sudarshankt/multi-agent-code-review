# Test Gate & Auto-Fix Loop Architecture — Multi-Agent Code Review System

> **Audience:** Project evaluators & technical reviewers  
> **Scope:** Test runner, pytest clone-and-execute pipeline, auto-fixing test loop with LLM retry, SSE progress streaming  
> **Files covered:** `test_runner.py`, `test_fix/agent.py`, `test_fix.j2`, `fixes.py`, `fix.py`, `TestResultPanel.tsx`, `ReviewDetail.tsx`

---

## Table of Contents

1. [System Overview](#system-overview)
2. [TestRunner — Clone, Execute, Parse](#testrunner--clone-execute-parse)
3. [Graceful Degradation Contract](#graceful-degradation-contract)
4. [Test-Fixing Loop — Auto-Fix via LLM with Retry](#test-fixing-loop--auto-fix-via-llm-with-retry)
5. [Pytest Output Parser](#pytest-output-parser)
6. [TestFixAgent — Fixing Only Tests, Never Source](#testfixagent--fixing-only-tests-never-source)
7. [Frontend — TestGate UI & Fix Progress](#frontend--testgate-ui--fix-progress)
8. [SSE Eventing for the Fix Loop](#sse-eventing-for-the-fix-loop)
9. [End-to-End Data Flow](#end-to-end-data-flow)
10. [Design Decisions & Trade-offs](#design-decisions--trade-offs)

---

## System Overview

The test gate subsystem validates that AI-generated code fixes do not break existing functionality. It operates in **two phases**:

1. **Phase 1 — Test Gate:** The user triggers a one-shot pytest run against the PR branch (which already has committed fixes). Results are displayed with pass/fail counts and full pytest output.

2. **Phase 2 — Auto-Fix Loop:** If tests fail, the user can invoke an LLM-powered retry loop that identifies failing test files, generates targeted fixes (test code only — never source code), commits them, and re-runs tests. This loop repeats until all tests pass or a retry limit is reached.

```
Phase 1:                   Phase 2:
POST /fixes/run-tests      POST /fixes/fix-tests
       │                         │
       ▼                         ▼
  TestRunner.run_tests()    ┌─────────────────────────┐
       │                    │  _run_test_fix_loop()   │
       ▼                    │                         │
  clone branch              │  while retries < 3:     │
  run pytest                │    run_tests()          │
  parse results             │    parse failures       │
  publish SSE               │    clone branch         │
       │                    │    fix via LLM          │
       ▼                    │    commit fixes         │
  UI shows pass/fail        │    re-test              │
                            │  publish final SSE      │
                            └─────────────────────────┘
```

---

## TestRunner — Clone, Execute, Parse

**File:** `src/services/test_runner.py`

The TestRunner performs a shallow clone of the PR branch into a temp directory, runs pytest against it, and parses the results. All operations are asynchronous; temp directories are cleaned up in `finally` blocks.

### Python Executable Resolution

The runner uses a dedicated `_resolve_venv_python()` function that resolves the venv Python from `sys.prefix`, not `sys.executable`. On macOS (and some Linux setups), `sys.executable` can resolve through symlinks to the bare framework Python interpreter, which lacks `pytest` and project dependencies. Using `sys.prefix` ensures the runner always uses the Python that has the full project environment:

```python
def _resolve_venv_python() -> str:
    venv_bin = Path(sys.prefix) / "bin" / "python"
    if venv_bin.is_file():
        return str(venv_bin)
    if Path(sys.executable).is_file():
        return sys.executable
    return "python"
```

### Clone Strategy

```
git clone --depth 1 --branch {branch} --single-branch {url} {tmp_dir}
```

- **`--depth 1`:** Shallow clone — fast, minimal data transfer.  
- **`--single-branch`:** Only the PR branch, not the full repository history.  
- **Authenticated URL:** Uses `GITHUB_TOKEN` via `x-access-token:{token}@{host}/{owner}/{repo}.git` for private repositories.

Clone timeout: 60 seconds. Timeout or failure → graceful skip (test gate proceeds without blocking).

### Test Execution

```
{venv_python} -m pytest --tb=short -q --no-header {clone_dir}/tests
```

- **Target:** The command points pytest at the `tests/` subdirectory when one exists, otherwise the clone root. This respects standard repository layouts.
- **`--tb=short`:** Compact tracebacks — enough detail for the LLM and the human reviewer, without bloated output.
- **`--no-header`:** Suppresses the pytest version banner to keep output concise.
- **`cwd=clone_dir`:** pytest runs from within the clone so `pyproject.toml` / `conftest.py` are discovered correctly.
- **PYTHONPATH:** The venv Python already has project dependencies installed, so test imports of `src.` modules succeed.

### No-Tests Diagnosis

When pytest reports exit code 5 (no tests collected), the runner automatically performs a second diagnostic pass:

```
{venv_python} -m pytest --collect-only -v --no-header {clone_dir}/tests
```

This `--collect-only -v` output is appended to the main output and surfaced in both server logs (`pytest_no_tests_diagnosis`) and the UI's pytest output expander. It reveals *why* no tests were found — empty test files, missing conftest.py, import errors, or a genuinely testless repository.

---

## Graceful Degradation Contract

The test gate is designed to **never block the user** due to infrastructure issues. Only actual test assertion failures produce a `FAILED` status. All other scenarios result in a `SKIPPED` status with a clear reason:

| Scenario | Exit Code | Result | UI Message |
|----------|-----------|--------|------------|
| Git clone fails | — | `SKIPPED` | "git clone failed — proceeding without test gate" |
| Clone timeout (60s) | — | `SKIPPED` | "git clone timeout" |
| No tests found | 5 | `SKIPPED` | "no tests found in repository" |
| Missing dependencies (ImportError) | 2 | `SKIPPED` | "test collection failed (missing dependencies)" |
| Pytest timeout (120s) | — | `SKIPPED` | "pytest timed out" |
| All tests pass | 0 | `PASSED` | "All N tests passed — committed fixes look safe" |
| Tests fail | 1 | `FAILED` | "N tests failed (M passed) — the committed fixes may have broken something" |

---

## Test-Fixing Loop — Auto-Fix via LLM with Retry

**File:** `src/api/endpoints/fixes.py` | Function: `_run_test_fix_loop()`

The fix loop is the heart of Phase 2. It iteratively runs tests, identifies failures, fixes test code via LLM, commits, and re-tests — up to a configurable maximum of 3 iterations.

### Loop Algorithm

```
iteration = 0
while iteration < MAX_RETRIES (3):
    iteration += 1

    # 1. RUN TESTS
    result = TestRunner.run_tests(owner, repo, branch)
    publish SSE: test_run_update + test_fix_iteration

    # 2. ALL PASS → DONE
    if result.passed and not result.skipped:
        publish SSE: test_fix_complete status=all_passed
        return

    # 3. PARSE FAILURES
    failing = parse_failing_files(result.stdout)
    if not failing:
        publish SSE: test_fix_complete status=cannot_fix
        return

    # 4. CLONE & READ FAILING FILES
    tmp_dir = await _clone_review_branch(...)
    for each failing file:
        code = _read_clone_file(tmp_dir, file_path)
        if not found: try alternate paths (tests/, test/, root)
        if still not found: skip with notification

    # 5. FIX EACH FILE VIA LLM
    for each failing file:
        success, fixed_code = TestFixAgent.fix_file(code, failure_output)
        if success: to_commit[file_path] = fixed_code
        publish SSE: test_fix_file status=fixed|skipped

    # 6. COMMIT ALL FIXES
    if to_commit:
        GitService.commit_fixes(owner, repo, branch, to_commit, message)
        publish SSE: test_fix_committed
    else:
        publish SSE: test_fix_complete status=no_progress
        break

# MAX RETRIES EXHAUSTED
publish SSE: test_fix_complete status=max_retries
```

### File Path Resolution

Pytest output contains absolute paths from the temp clone directory (e.g., `/var/folders/.../pr-review-test-XXX/tests/unit/test_user_manager.py`). However, each iteration creates a **new** clone (the previous one was cleaned up). The `parse_failing_files()` function normalizes these absolute paths to repo-relative paths (e.g., `tests/unit/test_user_manager.py`) so they resolve correctly against any clone directory.

If a normalized path doesn't resolve against the new clone, the loop tries alternate layouts:
1. Strip `tests/` prefix (try at repo root)
2. `tests/{filename}` (reconstruct from filename)
3. `test/{filename}` (alternative directory name)

This handles repositories with non-standard test directory structures.

### Commit Message Convention

```
[pr-review] GENAI=YES: fix {N} failing test(s) — iteration {K}
```

Each iteration produces a single commit (all fixed files batched together). The iteration counter in the commit message provides an audit trail.

### Termination Guarantees

The loop terminates in all cases:
- ✅ All tests pass → `all_passed`
- ❌ No failures to fix (skipped, no tests) → `cannot_fix`
- ❌ No progress between iterations (LLM couldn't fix any file) → `no_progress`
- ❌ Max retries (3) reached → `max_retries`
- ❌ Clone failure, commit failure, unexpected error → loop breaks

---

## Pytest Output Parser

**File:** `src/agents/test_fix/agent.py` | Function: `parse_failing_files()`

The parser extracts `{file_path: failure_details}` mappings from pytest output. It handles two output styles:

### Style 1 — Summary Lines (`-q` flag)

```
FAILED tests/test_auth.py::test_login - AssertionError: assert 1 == 2
FAILED tests/test_api.py::test_endpoint - ValueError: ...
```

### Style 2 — Section Headers (`--tb=short`)

```
______________________ test_login _______________________
tests/test_auth.py:42: in test_login
    assert result == expected
E   AssertionError: assert 1 == 2
```

The parser handles both styles and provides a combined failure output per file (trimmed to 4,000 characters to stay within LLM context limits).

### Path Normalization

The `_normalize_path()` function converts any path format to a repo-relative form:

| Input | Output |
|-------|--------|
| `/var/folders/.../pr-review-test-XXX/tests/unit/test_auth.py` | `tests/unit/test_auth.py` |
| `../../../../../../../var/folders/.../tests/unit/test_auth.py` | `tests/unit/test_auth.py` |
| `tests/unit/test_auth.py` (already relative) | `tests/unit/test_auth.py` |

The function uses `rfind("/tests/")` (last occurrence) to avoid matching `tests` segments in the temp path prefix itself, and falls back to filename extraction for non-standard layouts.

---

## TestFixAgent — Fixing Only Tests, Never Source

**File:** `src/agents/test_fix/agent.py`

The TestFixAgent is a lightweight LLM-based fixer that is **strictly scoped** to test files. It's designed as a separate agent from the main FixAgent because its constraints are fundamentally different:

| Aspect | FixAgent | TestFixAgent |
|--------|----------|-------------|
| **Modifies** | Source files | Test files only |
| **Premise** | Fix the vulnerability/bug | Source fix is correct — update test to match |
| **Constraints** | Don't break the public contract | Don't modify source code, don't delete tests, don't weaken assertions |
| **Prompt** | `fix.j2` | `test_fix.j2` |
| **Validation** | Python `compile()` | Python `compile()` |

### Prompt Contract

The `test_fix.j2` prompt explicitly frames the situation: the source code fix was reviewed and approved — it's correct. The tests that are failing need to be updated to match the new behavior, not the other way around.

Key rules enforced in the prompt:
- **Never modify source code** — test files only.
- **Don't delete test cases** — preserve coverage.
- **Don't weaken assertions** unless the old assertion was testing incorrect (now-fixed) behavior.
- **Preserve test structure** — same function names, fixtures, parametrize decorators.
- **`changed: false`** only when fixing requires modifying source code.

### Validation

Every fixed test file is validated via Python's `compile()` before being accepted. If the LLM produces syntactically invalid code, the fix is rejected and the file is skipped for that iteration.

---

## Frontend — TestGate UI & Fix Progress

### TestResultPanel Component

**File:** `dashboard/src/components/TestResultPanel.tsx`

The component manages four visual states:

| State | Display |
|-------|---------|
| **Idle (can't run)** | Gray text: "Apply your approved fixes first." |
| **Ready to run** | Blue "Run Tests" button enabled |
| **Running** | Spinner + "Cloning the branch and running pytest…" |
| **Completed — Passed** | Green banner: "All N tests passed." |
| **Completed — Failed** | Red banner: "N tests failed (M passed)" + "Fix Failing Tests" button |
| **Completed — Skipped** | Yellow banner: "Could not run tests: {reason}" |
| **Fix Loop Running** | Amber progress bar: "Iteration N/3 — fixing files…" + per-file status cards |

### Fix Progress in the UI

During the fix loop, SSE events update the UI in real time. The `TestResultPanel` shows:

1. **Iteration progress:** "Iteration 1/3 — running tests…" → "Iteration 1/3 — generating fixes…"
2. **Per-file status:** Each file being fixed shows a card with:
   - ✓ Green: "Fixed — {explanation}"  
   - ○ Gray: "Skipped — {reason}"
3. **Commit confirmation:** After fixes are committed, a green card shows the abbreviated commit SHA.
4. **Final result:** After the loop completes, the full test run summary updates in the UI.

### ReviewDetail Integration

**File:** `dashboard/src/pages/ReviewDetail.tsx`

The ReviewDetail page tracks fix-loop state separately from the one-shot test run:

- `testFixLoading` — whether the loop is in progress
- `testFixProgress` — current SSE event for UI rendering
- `handleFixTests()` — triggers the loop via `POST /fixes/fix-tests`
- SSE event handler — processes `test_fix_iteration`, `test_fix_file`, `test_fix_committed`, `test_fix_complete` events

After the loop completes, an 800ms delayed re-fetch of the review ensures the UI picks up the final `TestRunSummary` from the backend.

---

## SSE Eventing for the Fix Loop

During the test-fixing loop, SSE events provide real-time progress:

| Event Type | Published When | Key Payload Fields |
|-----------|----------------|-------------------|
| `test_fix_iteration` | Each iteration starts | `{iteration, max, status, files[]}` |
| `test_fix_file` | Per-file fix attempt | `{iteration, file_path, status, explanation}` |
| `test_fix_committed` | Commit succeeds | `{iteration, files, commit_sha}` |
| `test_fix_complete` | Loop terminates | `{status, iterations, tests_passed, tests_failed, message}` |
| `test_run_update` | After each test run in the loop | `{status, tests_passed, tests_failed, output_tail, iteration}` |

The `test_run_update` event is reused from the one-shot test gate — its payload includes an `iteration` field during the fix loop so the UI can distinguish between a standalone test run and a loop iteration.

---

## End-to-End Data Flow

### Phase 1 — One-Shot Test Run

```
User clicks "Run Tests"
       │
       ▼
POST /fixes/run-tests → 202 Accepted
       │
       ▼
asyncio.create_task(_run_test_gate)
       │
       ▼
TestRunner.run_tests(owner, repo, branch)
       ├── _make_clone_url() — authenticated HTTPS URL
       ├── _clone() — git clone --depth 1 --single-branch
       ├── _run_pytest() — {venv_python} -m pytest --tb=short -q
       │      └── (if exit_code==5) → _diagnose_no_tests() — pytest --collect-only -v
       └── _parse_result() — exit code analysis
       │
       ▼
_publish SSE: test_run_update
       │
       ▼
Store TestRunSummary on review.test_run
       │
       ▼
UI updates: TestResultPanel shows pass/fail/skipped
```

### Phase 2 — Auto-Fix Loop

```
User clicks "Fix Failing Tests"
       │
       ▼
POST /fixes/fix-tests → 202 Accepted
       │
       ▼
asyncio.create_task(_run_test_fix_loop)
       │
       ▼
Loop (max 3 iterations):
       │
       ├── TestRunner.run_tests(owner, repo, branch)
       │      → publish SSE: test_fix_iteration + test_run_update
       │
       ├── parse_failing_files(result.stdout)
       │      → {tests/unit/test_auth.py: failure_details, ...}
       │
       ├── _clone_review_branch() → tmp_dir
       │
       ├── For each failing file:
       │      ├── _read_clone_file(tmp_dir, file_path)
       │      ├── TestFixAgent.fix_file(code, failure_output)
       │      └── publish SSE: test_fix_file (status=fixed|skipped)
       │
       ├── If fixes generated:
       │      ├── GitService.commit_fixes() → single commit
       │      └── publish SSE: test_fix_committed
       │
       └── If no fixes → break (no_progress)
       │
       ▼
publish SSE: test_fix_complete (status=all_passed|max_retries|cannot_fix|no_progress)
       │
       ▼
UI re-fetches review → updated test_run displayed
```

---

## Design Decisions & Trade-offs

### Separate Clone Per Iteration

Each iteration of the fix loop creates a fresh clone. This ensures every test run operates on the latest committed state and avoids any state leakage between iterations.

✅ **Correctness:** No stale directory state from previous iterations.  
⚠️ **Latency:** Each clone adds ~1 second. Acceptable at 3 max iterations.

### Test-Only Fix Scope

The TestFixAgent is deliberately scoped to test files only. It cannot modify source code — the source fixes were already reviewed and approved by the human. This constraint is enforced at three levels: (1) the prompt template, (2) the agent implementation (no access to source file paths), and (3) the commit loop (only test file paths are committed).

✅ **Safety:** Approved source fixes are never silently overwritten.  
✅ **Separation of concerns:** Source fixing and test fixing are distinct operations.

### Graceful Degradation at Every Boundary

The test gate never blocks the user. Clone failures, missing dependencies, timeouts, and even pytest crashes all result in `SKIPPED` status. Only actual test assertion failures produce `FAILED`. This de-risks the deployment: the system remains usable even when the test infrastructure is incomplete.

### No Local Git Operations

Both the test runner and the fix loop use shallow HTTPS clones (`git clone --depth 1`). No local git state is maintained. Temp directories are always cleaned up in `finally` blocks. Disk usage during testing is bounded by the repository size (shallow clone, no history).

### LLM as Test Fixer, Not Test Deleter

The prompt explicitly forbids deleting tests and weakening assertions. This is a deliberate design choice: an LLM that "fixes" tests by removing failing ones is worse than one that refuses to fix. The `changed: false` escape hatch ensures the loop terminates when genuine fixes are impossible.

### Retry Limit with Termination Guarantees

The 3-iteration cap prevents infinite loops. Combined with the "no progress" check (LLM couldn't fix any file → stop immediately), the loop always terminates — either because tests pass, no more progress is possible, or the budget is exhausted.

### SSE Stream Lifetime

The SSE stream persists for the connection lifetime (browser tab), not for the review lifecycle. This is critical because the test fix loop happens *after* the review is COMPLETED. Without persistent SSE, test results and fix progress would never reach the UI.

---
