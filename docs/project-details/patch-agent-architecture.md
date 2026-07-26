# Patch Agent & Human-in-the-Loop Architecture — Multi-Agent Code Review System

> **Audience:** Project evaluators & technical reviewers  
> **Scope:** FixAgent, human-in-the-loop diff review, approve/reject workflow, GitHub commit pipeline  
> **Files covered:** `fix/agent.py`, `fix.j2`, `test_fix.j2`, `fixes.py`, `fix.py`, `review.py`, `git_service.py`, `DiffViewer.tsx`, `ProposedFixCard.tsx`, `ReviewDetail.tsx`

---

## Table of Contents

1. [System Overview](#system-overview)
2. [FixAgent — From Direct Commits to Proposals](#fixagent--from-direct-commits-to-proposals)
3. [LLM Prompt Design — Safe Fixing by Contract](#llm-prompt-design--safe-fixing-by-contract)
4. [Human-in-the-Loop — The Approve/Reject Workflow](#human-in-the-loop--the-approvereject-workflow)
5. [Deduplication & Severity Gating](#deduplication--severity-gating)
6. [GitHub Commit Pipeline](#github-commit-pipeline)
7. [Frontend — Diff Viewer & Fix Review UI](#frontend--diff-viewer--fix-review-ui)
8. [SSE Eventing — Real-Time Fix Streaming](#sse-eventing--real-time-fix-streaming)
9. [End-to-End Data Flow](#end-to-end-data-flow)
10. [Design Decisions & Trade-offs](#design-decisions--trade-offs)

---

## System Overview

The patch subsystem transforms raw analysis findings into concrete code fixes, but **never** directly commits them. Instead, every proposed fix passes through a human-in-the-loop review step before touching the PR branch. This architecture addresses the fundamental tension in AI code review: the LLM can generate fixes, but only a human developer should decide whether those fixes are correct and appropriate.

```
Analysis Agents (Security, Bug, Style, Performance)
           │
           ▼
     FixAgent.generate_proposals()
           │
           ▼
    ProposedFix objects (with unified diffs)
           │
           ▼
    SSE stream → Dashboard UI (DiffViewer)
           │
           ▼
    Human review (Approve / Reject per diff)
           │
           ▼
    FixAgent.commit_approved() → GitHub REST API
```

---

## FixAgent — From Direct Commits to Proposals

**File:** `src/agents/fix/agent.py` | **Model:** `src/models/fix.py`

The FixAgent was originally designed to generate fixes and immediately commit them to the PR branch via GitHub's REST API. We refactored it into a **two-stage pipeline**:

### Stage A: `generate_proposals()` — No GitHub Calls

```
generate_proposals(files, findings, review_id)
   │
   ├── 1. Filter findings: only critical/high severity (FIXABLE_SEVERITIES)
   ├── 2. Group by category: security → bug → style → performance
   ├── 3. Limit: max 10 files per category (MAX_FIX_FILES_PER_CATEGORY)
   │
   └── Per file:
       ├── render("fix.j2") → LLM generates fixed code
       ├── Validate Python syntax with compile()
       ├── Skip if no actual change (fixed_code == original)
       ├── Generate unified diff via difflib
       └── Return ProposedFix object
```

Each `ProposedFix` carries:
- `id` — UUID for tracking across SSE events
- `diff` — Unified diff string from difflib (server-side, never LLM-generated)
- `original_code` / `fixed_code` — Full file contents
- `explanation` — One-line LLM summary of what changed
- `status` — PENDING → APPROVED/REJECTED → COMMITTED
- `category` — Which agent discovered the issue (security, bug, style, performance)

### Stage B: `commit_approved()` — Gate Before GitHub

```
commit_approved(proposals, owner, repo, branch)
   │
   ├── Filter: only proposals with status == APPROVED
   ├── Group by category
   ├── Per category: call git.commit_fixes() → 1 commit per category
   └── Update each proposal's status → COMMITTED + commit_sha
```

### Diff Generation (Server-Side)

Diffs are generated using Python's `difflib.unified_diff`, not by the LLM. This guarantees accuracy — the diff is computed deterministically between the original and the LLM-generated fixed code:

```python
def _make_diff(original: str, fixed: str, file_path: str) -> str:
    return "\n".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    ))
```

---

## LLM Prompt Design — Safe Fixing by Contract

**File:** `src/prompts/templates/fix.j2`

The fix prompt was redesigned from a minimal 20-line template into a **contract-based prompt** that balances safety with effectiveness.

### Evolution of Constraints

**v1 (original):** "Rewrite the file to resolve findings while preserving unrelated behavior." — Too vague, led to either over-cautious `changed: false` responses or overly aggressive rewrites.

**v2 (rigid):** 7 hard "MUST NOT" rules — too restrictive, caused the LLM to bail out on any fix that touched more than one line.

**v3 (current — balanced):** One core constraint plus encouragement:

```
CORE RULE: Do not change the public contract other code relies on.

ENCOURAGED TO:
- Add new imports if the fix needs them
- Add helper logic, validation, or error handling near the fix site
- Touch more than just the flagged line(s) when the bug requires restructuring
- Rename private/local variables introduced by your fix

AVOID:
- Rewriting unrelated code
- Changing function/method signatures
- Deleting functionality instead of correcting it

"changed": false ONLY when a correct fix is genuinely impossible
without breaking the public contract.
```

### Test-Fixing Prompt

**File:** `src/prompts/templates/test_fix.j2`

A separate, more restrictive prompt for the test-fixing loop. This prompt assumes the source code fix is **already correct and approved** — the test code must be updated to match:

```
CRITICAL RULES:
1. You may ONLY modify the test file — NEVER modify source code
2. Fix the test to match the new expected behavior from the fix
3. Do NOT delete test cases or weaken assertions
4. Preserve test structure: same function names, fixtures, decorators
5. "changed": false ONLY if fixing requires modifying source code
```

### JSON Output Contract

Both fix prompts enforce the same output schema:

```json
{
  "changed": true | false,
  "fixed_code": "<complete new file content>",
  "explanation": "<one-line summary of changes>"
}
```

The `compilable()` syntax validation runs on every fixed Python file before it reaches the commit stage.

---

## Human-in-the-Loop — The Approve/Reject Workflow

### API Endpoints

**File:** `src/api/endpoints/fixes.py`

Three endpoints form the review workflow:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/reviews/{id}/fixes` | List all proposals with diffs, status, and counts |
| `PATCH` | `/reviews/{id}/fixes/{fix_id}` | Approve or reject a single proposed fix |
| `POST` | `/reviews/{id}/fixes/apply` | Commit all approved fixes to GitHub |

### Workflow State Machine

```
PENDING ──approve──→ APPROVED ──apply──→ COMMITTED
   │                    │
   └──reject──→ REJECTED │
                         └──no longer eligible for apply
```

Key constraints:
- **COMMITTED** and **FAILED** fixes cannot be re-reviewed (409 Conflict)
- **Apply** requires at least one APPROVED fix (400 if none)
- All fixes must be decided (approved or rejected) before applying is enabled in the UI

### In-Memory Storage

Proposals are stored on the `Review` model (`review.proposed_fixes`). The `Review` object lives in the in-memory `_reviews` dict. Since `Review` carries the proposals list, no separate storage is needed. Properties `pending_fix_count`, `approved_fix_count`, and `committed_fix_count` provide fast status summaries.

---

## Deduplication & Severity Gating

**File:** `src/agents/deduplication.py`

Before the FixAgent runs, findings from all four analysis agents are deduplicated:

### Similarity Detection

Two findings are considered duplicates if:
1. **Same file + same line range + title similarity ≥ 0.7** (SequenceMatcher, difflib), OR
2. **Title similarity ≥ 0.85** regardless of location

### Best-Candidate Selection

From each duplicate group, the best finding is selected by:
1. Higher severity rank (critical=5 → info=1)
2. Higher confidence (high > medium > low)
3. Best agent category match via keyword scoring

### Severity Gate

Only findings with `FIXABLE_SEVERITIES = ("critical", "high")` are eligible for auto-fixing. Low, medium, and info findings are reported to the dashboard but not sent to the FixAgent.

---

## GitHub Commit Pipeline

**File:** `src/services/git_service.py`

Fixes are committed to the PR branch via the GitHub REST API — **no local git clone is needed**. Each category gets its own commit for clarity and atomic rollback.

### Commit Sequence (6 API calls per category)

```
Step 1: GET  /repos/{owner}/{repo}/git/ref/heads/{branch}
             → head_sha

Step 2: GET  /repos/{owner}/{repo}/git/commits/{head_sha}
             → base_tree_sha

Step 3: POST /repos/{owner}/{repo}/git/blobs           (one per file)
             body: {"content": base64(content), "encoding": "base64"}
             → blob_sha per file

Step 4: POST /repos/{owner}/{repo}/git/trees
             body: {"base_tree": base_tree_sha, "tree": [{path, mode, type, sha}]}
             → new_tree_sha

Step 5: POST /repos/{owner}/{repo}/git/commits
             body: {"message": "[pr-review] GENAI=YES: fix {category} ({N} files)",
                    "tree": new_tree_sha, "parents": [head_sha]}
             → new_commit_sha

Step 6: PATCH /repos/{owner}/{repo}/git/refs/heads/{branch}
              body: {"sha": new_commit_sha, "force": false}
```

### Enterprise Compliance

- Content is **base64-encoded** (not UTF-8) — required by enterprise pre-receive hooks.
- Every commit message contains **`GENAI=YES`** for audit trail and enterprise policy compliance.
- Commit order: security → bug → style → performance (most critical first).

---

## Frontend — Diff Viewer & Fix Review UI

### DiffViewer Component

**File:** `dashboard/src/components/DiffViewer.tsx`

Parses a unified diff string and renders it as a color-coded table:

| Line Type | Background | Border | Prefix |
|-----------|-----------|--------|--------|
| Added (`+`) | `bg-green-50 text-green-900` | Left green `border-l-4` | `+` |
| Removed (`-`) | `bg-red-50 text-red-900` | Left red `border-l-4` | `-` |
| Hunk (`@@`) | `bg-blue-50 text-blue-700` | None | (none) |
| Header (`+++`/`---`) | `bg-gray-100 text-gray-500` | None | (none) |
| Context | `bg-white text-gray-800` | None | ` ` (space preserved) |

The diff viewer is scrollable (max 384px height) with horizontal overflow for wide files. The file path is shown in a dark header bar mimicking IDE tabs.

### ProposedFixCard Component

**File:** `dashboard/src/components/ProposedFixCard.tsx`

Each proposal renders as a card with:
- **Header:** File path (monospace), category badge (color-coded), status badge
- **Body:** Collapsible `DiffViewer` (expanded by default)
- **Footer:** Approve / Reject buttons — green/red borders for visual feedback
- **State:** PENDING (gray border) → APPROVED (green border + green tint) → COMMITTED (green border + commit SHA)

The approve and reject buttons persist their state after clicking — approved cards stay approved with a filled green button, rejected cards dim with a strikethrough effect.

### ReviewDetail Integration

**File:** `dashboard/src/pages/ReviewDetail.tsx`

The "Proposed Fixes" section appears after the findings table and shows:
1. **Status bar:** "(N approved · M pending · K committed)"
2. **All-decided gate:** "Apply Approved Fixes" button is **disabled** until every fix is decided (shows a yellow banner: "Approve or reject all N proposed fixes before you can apply them")
3. **Commit success:** After applying, shows the commit SHA per category in green banners
4. **Test gate:** Enabled only AFTER commits (committedCount > 0)

---

## SSE Eventing — Real-Time Fix Streaming

**File:** `src/api/endpoints/sse.py`

The SSE stream stays open for the entire review lifecycle — not just the analysis phase. This means fix review events arrive in real time:

| Event Type | Published When | Payload |
|-----------|----------------|---------|
| `proposed_fix` | FixAgent generates a proposal | `{fix_id, category, file_path, diff, explanation, status}` |
| `fix_status_changed` | User approves/rejects | `{fix_id, old_status, new_status}` |
| `fixes_committed` | Commit succeeds | `{committed_count, failed_count, commit_shas}` |

**Critical design decision:** Unlike earlier implementations, the SSE stream **never auto-closes** on a terminal review status. The pipeline completes (status=COMPLETED) but the user still needs live updates for fix approval, commit, and test gate events. The stream only closes when the browser tab disconnects (FastAPI request cancellation).

---

## End-to-End Data Flow

```
1. PR submitted → 4 analysis agents run in parallel
       │
2. aggregate_findings → deduplicate (deduplication.py)
       │
3. should_apply_fixes? → YES (findings exist)
       │
4. FixAgent.generate_proposals()
       ├── Filter: only critical/high severity
       ├── Group by category
       ├── Per file: LLM generates fix → validate syntax → generate diff
       └── Return list of ProposedFix objects
       │
5. SSE streams proposed_fix events → Dashboard UI
       │
6. User reviews each diff:
       ├── Approve (PATCH /fixes/{id} action=approve)
       └── Reject (PATCH /fixes/{id} action=reject)
       │
7. User clicks "Apply Approved Fixes":
       ├── POST /fixes/apply
       ├── FixAgent.commit_approved()
       ├── GitService.commit_fixes() per category (6 REST API calls each)
       ├── SSE fires fixes_committed
       └── UI shows commit SHAs per category
       │
8. (Optional) User clicks "Run Tests":
       ├── POST /fixes/run-tests
       ├── TestRunner: clone branch → pytest → publish results via SSE
       └── UI shows pass/fail/skipped banner
```

---

## Design Decisions & Trade-offs

### Two-Stage Fix Pipeline (Propose → Approve → Commit)

The original design committed fixes immediately during the LangGraph pipeline. The refactored design separates generation from commitment. This introduces a human decision point — slower, but zero risk of auto-committing broken code.

✅ **Safety:** No code is committed without explicit human approval.  
⚠️ **Latency:** The review-to-commit cycle requires user interaction (acceptable for the current MVP).

### Server-Side Diff Generation

Diffs are computed via `difflib.unified_diff` rather than trusting the LLM to generate accurate diffs. The LLM only produces `fixed_code` — the diff is a deterministic function of original → fixed.

✅ **Reliability:** Diffs are always accurate. No LLM hallucination in the diff output.  
✅ **Consistency:** Human reviewers see a standard unified diff format they're familiar with.

### Single Commit Per Category

Fixes are grouped by category (security → bug → style → performance) and committed separately, each with a distinct commit message.

✅ **Atomicity:** Each category can be rolled back independently.  
✅ **Audit trail:** Clear separation between "fixed security issues" and "fixed style issues."  
⚠️ **Latency:** Each category requires 6 sequential REST API calls. A review generating fixes in all 4 categories is 24 API calls.

### No Local Clone (REST API Commits)

All git operations use the GitHub REST API rather than a local clone. The 6-step commit flow (GET ref → GET commit → POST blobs → POST tree → POST commit → PATCH ref) is stateless and works with GitHub Enterprise.

✅ **Deployment simplicity:** No disk I/O, no clone management, no branch tracking.  
✅ **Enterprise compatibility:** Token-based auth, base64 encoding, GENAI=YES markers.  
⚠️ **Rate limits:** A large fix batch triggers many sequential API calls. Mitigated by the 10-file-per-category cap.

### All-Decided Gate Before Commit

The UI prevents the "Apply" button from being enabled until every proposed fix has been explicitly approved or rejected. This prevents accidental commits of unreviewed code.

✅ **Intentionality:** No fix is applied without an explicit human decision.  
⚠️ **UX friction:** Users must click through every diff. Mitigated by clear progress indicators ("N still pending").

### SSE Stream Lifetime

The SSE connection is never closed based on review status — it persists for the browser tab's lifetime. This ensures late-arriving events (test results, commit confirmations) are delivered to the UI.

✅ **Reliability:** No dropped events during post-review operations.  
⚠️ **Connection count:** Long-lived connections consume server resources. Acceptable for the MVP (in-memory storage, single-process backend).

---
