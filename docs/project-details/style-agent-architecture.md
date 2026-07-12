# Style Agent Architecture — Multi-Agent Code Review System

> **Audience:** Project evaluators & technical reviewers  
> **Scope:** Style analysis pipeline — Ruff linting, LLM readability review, deduplication  
> **Files covered:** `style/agent.py`, `style.j2`, `base.py`, `finding.py`, `parsing.py`, `_common.j2`

---

## Table of Contents

1. [System Overview](#system-overview)
2. [StyleAgent — The Two-Pass Analysis Pipeline](#styleagent--the-two-pass-analysis-pipeline)
3. [Pass 1: Ruff Deterministic Linting](#pass-1-ruff-deterministic-linting)
4. [Pass 2: LLM Readability & Maintainability Review](#pass-2-llm-readability--maintainability-review)
5. [Deduplication — Preventing Redundant Findings](#deduplication--preventing-redundant-findings)
6. [Static Triage — The Cost-Saving Skip Mechanism](#static-triage--the-cost-saving-skip-mechanism)
7. [Prompt Template Design](#prompt-template-design)
8. [Finding Source Attribution](#finding-source-attribution)
9. [End-to-End Data Flow](#end-to-end-data-flow)
10. [Design Decisions & Trade-offs](#design-decisions--trade-offs)

---

## System Overview

The style agent is one of four parallel analysis agents in the multi-agent code review system. Unlike the security agent — which always invokes the LLM because vulnerabilities like IDOR have no static signature — the style agent follows a **deterministic-conditional-philosophy**: it runs Ruff first, and **only invokes the LLM if Ruff or heuristics detect structural signals** warranting deeper review. This design saves significant API cost while maintaining comprehensive coverage.

```
┌──────────────────────────────────────────────────────┐
│                  BaseAnalysisAgent                   │
│       Concurrency · Triage · Isolation · Metrics     │
├──────────────────────────────────────────────────────┤
│                    StyleAgent                        │
│  Pass 1: Ruff (E,W,F rules) → FindingSource.LINTER   │
│  Pass 2: LLM readability review → FindingSource.LLM  │
│  Merge: Ruff findings + deduped LLM findings         │
├──────────────────────────────────────────────────────┤
│            Supporting Infrastructure                  │
│        Prompts (style.j2) · Parsing (parsing.py)      │
└──────────────────────────────────────────────────────┘
```

**Key differentiator from other agents:** The style agent is the only agent that can **truly skip the LLM** when static triage detects no actionable code structure. For a Python file containing only comments and blank lines, both Ruff returns empty and `_static_triage` returns `[]` — the LLM is never called.

---

## StyleAgent — The Two-Pass Analysis Pipeline

**File:** `src/agents/style/agent.py`

The `StyleAgent` implements a **two-pass analysis pipeline**: deterministic linting first, followed by a conditional LLM review. Ruff findings and LLM findings are merged with deduplication to produce a clean, non-redundant result set.

### Class Structure

```python
class StyleAgent(BaseAnalysisAgent):
    name = "style"  # AGENT_STYLE constant
    
    def __init__(self, llm: LLMService | None = None):
        self.llm = llm or get_llm_service()
```

The agent accepts an optional `LLMService` for testability — in production, the default factory `get_llm_service()` provides the real Anthropic-backed client. In unit tests, a `FakeLLMService` is injected for deterministic, cost-free execution.

### The `analyze()` Method

The `analyze()` method is the core pipeline. It executes in sequence:

1. **Ruff pass** — Runs `_run_ruff()` for `.py` files; non-Python files skip this step.
2. **Prompt assembly** — Renders the `style.j2` Jinja2 template with code, diff, and ruff hints.
3. **LLM invocation** — Calls `self.llm.complete_json(prompt)` for structured output.
4. **Deduplication** — Compares LLM finding titles against Ruff finding titles (case-insensitive), removing any duplicates.
5. **Merge** — Returns `ruff_findings + deduped_llm_findings`.

The Ruff-to-LLM hints bridge is critical: ruff findings are serialized as `{"start_line", "code", "title"}` tuples and injected into the prompt as a block listing “already reported issues.” This prevents the LLM from wasting tokens re-reporting issues Ruff already caught.

---

## Pass 1: Ruff Deterministic Linting

### Invocation (`_run_ruff`)

The Ruff pass runs as a **subprocess** against the code string via stdin:

```python
subprocess.run(
    ["ruff", "check", "--output-format", "json", "--select", "E,W,F",
     "--stdin-filename", file_path, "-"],
    input=code.encode(),
    capture_output=True,
    timeout=10,
)
```

**Key design decisions in this invocation:**

| Parameter | Purpose |
|---|---|
| `--output-format json` | Machine-parseable output; no regex scraping of human-readable text |
| `--select E,W,F` | Only error, warning, and pyflakes rules — excludes formatting rules (RUF, I, etc.) that would overlap with opinionated LLM feedback |
| `--stdin-filename {file_path}` | **Critical**: without this, ruff falls back to scanning the project directory instead of stdin — a bug discovered and fixed during integration testing |
| `-` (trailing dash) | Explicitly reads from stdin |
| `timeout=10` | Prevents hung ruff processes from blocking the review pipeline |

### Error Handling

Three failure modes are explicitly caught:

1. **`FileNotFoundError`** — Ruff binary not installed. Logged at `debug` level; returns `[]` so LLM pass still runs.
2. **`TimeoutExpired`** — Ruff hung (extremely rare for lint-size inputs). Returns `[]`.
3. **JSON decode failure** — Ruff produced non-JSON output (e.g., a deprecation warning on stderr that leaked into stdout). Returns `[]`.

All three are **non-fatal**: the LLM pass continues regardless.

### Finding Construction

Each Ruff finding is converted to a `Finding` Pydantic model:

```python
Finding(
    category=Category.STYLE,           # Fixed
    severity=Severity.LOW,             # All linter issues are LOW
    title=f"{code_val}: {msg[:50]}",   # e.g. "F401: `os` imported but unused"
    description=msg,                   # Full untruncated message
    location=Location(
        file_path=file_path,
        start_line=line,
        end_line=line
    ),
    source=FindingSource.LINTER,       # Explicit LINTER tag
)
```

**Design notes:**

- **Title truncation:** Messages longer than 50 characters are truncated in the title to keep prompt hints compact. The full message is preserved in `description`.
- **Missing `code` fallback:** If a Ruff item lacks a `code` field, `"?"` is used — ensuring a title is always generated.
- **Line-less items skipped:** Ruff items without a `row` in their location are silently dropped (they can't be linked to source).
- **Non-dict items skipped:** Any non-dict element in Ruff's JSON array is ignored — defensive against unexpected output formats.
- **Source tagging:** Explicitly set to `FindingSource.LINTER`, enabling the dashboard and deduplication engine to distinguish linter findings from LLM findings.

### Edge Case: Non-Python Files

For files that don't end with `.py` (`.js`, `.ts`, `.go`, etc.), Ruff is skipped entirely. The LLM pass still runs, but the prompt won't contain Ruff hints. This is by design — Ruff is Python-only, and the LLM handles style review for all supported languages.

---

## Pass 2: LLM Readability & Maintainability Review

### Role Scoping

The LLM is instructed to focus on **subjective code quality** — exactly the class of issues linters miss:

- **Unclear naming** — Misleading function/variable names, abbreviations that obscure meaning.
- **Dead code** — Commented-out blocks, unreachable code after returns, unused parameters that imply missing access control.
- **Missing docstrings** — Functions and classes that lack documentation where the context warrants it.
- **Inconsistent style** — Patterns that deviate from project conventions without justification.
- **Anti-patterns** — Mixed return types (`bytes | str`), functions that promise one thing but do another.

### Explicit Exclusion Zones

The prompt explicitly lists what **not** to report:

| Excluded | Reason |
|---|---|
| Security issues | Handled by `SecurityAgent` |
| Functional bugs | Handled by `BugDetectionAgent` |
| Performance problems | Handled by `PerformanceAgent` |
| Linter-detected style | Already reported by Ruff; listed in prompt as "do not duplicate" |

This scope isolation prevents agent overlap and ensures each finding is category-correct for the dashboard and deduplication engine.

### Ruff Hints as Negative Guidance

The prompt template renders Ruff findings as a bullet list:

```
Ruff already reported these style issues — do NOT duplicate them:
- L14 F401: `sentence_transformers.SentenceTransformer` import
- L33 W293: Blank line contains whitespace
```

This serves two purposes:
1. **Token savings** — The LLM doesn't waste output tokens on already-known issues.
2. **RAG-like grounding** — Seeing the Ruff issues gives the LLM context about what's already been flagged, so it can focus on deeper concerns.

---

## Deduplication — Preventing Redundant Findings

**Files:** `src/agents/style/agent.py` (inline logic), `src/agents/parsing.py`

After both passes complete, findings are merged with deduplication:

```python
ruff_titles = {f.title.lower() for f in ruff_findings}
deduped_llm = [
    f for f in llm_findings if f.title.lower() not in ruff_titles
]
return ruff_findings + deduped_llm
```

**Key characteristics:**

- **Case-insensitive matching** — `"W292: No newline at end of file"` matches `"W292: no newline at end of file"`.
- **Exact title matching** — Only exact title overlap triggers deduplication. A finding titled "Unused import `os` found in module" would NOT be deduped against Ruff's `"F401: \`os\` imported but unused"` — this is intentional, as only Ruff-style formatted titles (code + colon + message) are guaranteed to overlap.
- **Ruff wins** — When a conflict occurs, the Ruff finding is kept (it has precise line numbers and the `LINTER` source tag) and the LLM duplicate is dropped.
- **Ordering** — Ruff findings come first in the output list, followed by deduped LLM findings. This ensures deterministic, reproducible ordering.

**Why not use `title` deduplication in the shared `deduplication.py` module?** The style agent performs dedup locally because the comparison is specific to Ruff's title format (`CODE: message`). The shared deduplication engine (`src/agents/deduplication.py`) handles cross-agent deduplication (e.g., a finding that both Security and Bug agents report).

---

## Static Triage — The Cost-Saving Skip Mechanism

**Method:** `StyleAgent._static_triage()`

The style agent implements the `BaseAnalysisAgent` triage contract with a **cost-saving twist**: it can skip the LLM entirely.

### Triage Logic

```python
async def _static_triage(self, code, file_path, context=None):
    if any(token in code for token in ["import ", "def ", "class ", "return"]):
        return [{"type": "structure", "token": "python-structure"}]
    return []
```

The check is intentionally simple and fast:
- Presence of `import`, `def`, `class`, or `return` → **run LLM** (there's code worth reviewing).
- Absence of all four → **skip LLM** (empty files, comment-only files, pure data files).

### Integration with BaseAnalysisAgent

When `triage_enabled=True` (set by the orchestrator), `BaseAnalysisAgent.run()` calls `_static_triage` before `analyze()`. If it returns `[]` (empty list, meaning no structure detected):

1. A `files_bypassed` counter is incremented.
2. A structured log event `agent_triage_skipped` is emitted.
3. The file is skipped — no LLM call, no Ruff call (since Ruff is inside `analyze()`).

**Cost impact:** For a PR touching 20 files where 6 are pure configuration or empty templates, up to 6 LLM calls are saved — roughly 30% cost reduction.

### Why This Is Safe for Style

Unlike security (where vulnerabilities can hide in any code), style issues inherently require **code structure** to exist. If there are no functions, classes, imports, or return statements, there is nothing to review — no naming to critique, no dead code to flag, no docstrings to add. The triage check is conservative: even a single `def` statement triggers the full pipeline.

---

## Prompt Template Design

**File:** `src/prompts/templates/style.j2`

The style prompt is a Jinja2 template with conditional context layers:

```
You are a code reviewer focused on readability and maintainability.

**SCOPE**: Look for unclear naming, dead code, overly complex functions, missing
docstrings where warranted, inconsistent style, and anti-patterns. Focus on
issues a linter would NOT already catch.

**DO NOT REPORT**: Security issues, functional bugs, performance problems, or
linter-detected style problems (those are already listed below).

{% if ruff_issues %}
Ruff already reported these style issues — do NOT duplicate them:
{% for item in ruff_issues %}
- L{{ item.start_line }} {{ item.code }}: {{ item.title }}
{% endfor %}
{% endif %}

{% if diff %}
Diff for this file:
```diff
{{ diff }}
```
{% endif %}

File: {{ file_path }}
```
{{ code }}
```

Focus on issues introduced by the changes in the diff and use the full file
only for surrounding context.

{% include "_common.j2" %}
```

### Template Design Principles

**1. Role Scoping — Narrow and Explicit**

The LLM is instructed to focus exclusively on readability and maintainability. The "DO NOT REPORT" block enumerates three other agent domains (security, bugs, performance) to prevent scope creep.

**2. Negative Prompting via Ruff Hints**

Rather than just saying "don't report lint issues," the template shows the LLM exactly what Ruff found. This is more effective because the LLM can see the specific codes and messages, making it less likely to accidentally re-report a Ruff issue under different wording.

**3. Diff-First, Full-File as Context**

When a diff is available, the LLM is instructed to focus on **changes introduced by the diff** and use the full file only for surrounding context. This prevents flagging pre-existing style issues that aren't part of the PR's scope.

**4. Structured Output Contract**

The `_common.j2` partial enforces a JSON-only response with a fixed schema: `title`, `description`, `severity`, `confidence`, `start_line`, `end_line`, `suggestion`, `cwe_id`, `references`. Empty array `[]` if no issues found. The severity field in `_common.j2` supports all levels (`critical` through `info`), but the style prompt scopes the LLM to report only `low` and `info` — style issues are never critical or high.

---

## Finding Source Attribution

**File:** `src/models/finding.py`

Every finding carries a `source` field from the `FindingSource` enum:

```python
class FindingSource(str, Enum):
    LLM = "llm"              # Claude LLM generated
    AST_ANALYZER = "ast_analyzer"  # Python AST static analysis
    LINTER = "linter"        # Ruff or similar linter
```

The style agent is the only agent that populates **two different sources** within a single review:

| Source | Set by | When |
|---|---|---|
| `FindingSource.LINTER` | `StyleAgent._run_ruff()` | Ruff findings from the deterministic pass |
| `FindingSource.LLM` | `parsing.findings_from_llm()` | LLM-generated findings from Pass 2 |

### Why Source Attribution Matters

1. **Dashboard visibility** — The React dashboard can render linter findings differently from LLM findings (e.g., showing a Ruff icon vs. an AI icon).
2. **Confidence calibration** — Linter findings are 100% deterministic (no false positives within their rule set), while LLM findings carry confidence scores. The source tag lets consumers calibrate their trust level.
3. **Audit trail** — If a finding is disputed, the source tag immediately tells you whether it came from an automated tool or an AI model.
4. **Deduplication safety** — The deduplication engine uses source as one dimension when determining if two findings from different agents are actually the same issue.

### Bug Fixed: Source Was Defaulting to LLM

During the creation of unit tests, a bug was discovered: `_run_ruff()` was constructing Finding objects without setting `source`, causing it to default to `FindingSource.LLM`. This meant Ruff findings were indistinguishable from LLM findings in the output. The fix was adding `source=FindingSource.LINTER` explicitly in the `Finding()` constructor call.

---

## End-to-End Data Flow

```
BaseAnalysisAgent.run()
   │
   ├── Filter by SOURCE_EXTENSIONS
   ├── _static_triage()
   │     ├── Has import/def/class/return? → run LLM
   │     └── No structure? → SKIP (files_bypassed++)
   │
   ▼
StyleAgent.analyze(code, file_path, context)
   │
   ├── Pass 1: _run_ruff(code, file_path)
   │     ├── Is .py file? → ruff check --stdin-filename ... -
   │     │     ├── Success → parse JSON → list[Finding] with source=LINTER
   │     │     └── Error/not found → [] (non-fatal)
   │     └── Not .py? → skip ruff
   │
   ├── Build ruff_hints = [{start_line, code, title}, ...]
   │
   ├── Pass 2: render("style.j2") → prompt
   │     ├── Injects: file_path, code, diff, ruff_hints
   │     └── Includes _common.j2 (JSON output contract)
   │
   ├── LLM.complete_json(prompt) → payload
   │     └── findings_from_llm(payload, Category.STYLE, file_path)
   │           → list[Finding] with source=LLM
   │
   ├── Deduplication
   │     ├── Build set of Ruff finding titles (lowercased)
   │     └── Filter LLM findings: keep only non-matching titles
   │
   └── Merge & Return
         └── ruff_findings + deduped_llm_findings
```

---

## Design Decisions & Trade-offs

### Ruff as a Gate, Not a Replacement

Ruff handles the **mechanical** style issues (unused imports, trailing whitespace, line length) while the LLM handles **subjective** issues (naming, dead code, anti-patterns). This division of labor is deliberate:

- **Ruff is fast** — sub-millisecond for typical files.
- **Ruff is free** — no API costs.
- **Ruff is deterministic** — same input always produces the same output.
- **LLM is nuanced** — can detect misleading function names like `get_db_connection` that returns a dictionary.

### Why Ruff Runs via Subprocess, Not as a Library

Ruff is invoked via `subprocess.run()` rather than imported as a Python library. Rationale:

- **Process isolation** — A Ruff crash or memory leak cannot affect the review pipeline.
- **Version independence** — The installed Ruff binary is used; no risk of import conflicts.
- **Timeout safety** — The 10-second timeout is enforceable at the process level via `subprocess.run(timeout=10)`.
- **Consistency** — Same approach as Bandit in the security agent; shared pattern across the codebase.

### Why Only E/W/F Rules

The `--select E,W,F` flag limits Ruff to three rule categories:

| Prefix | Category | Examples |
|---|---|---|
| `E` | Error | `E501` (line too long), `E999` (syntax error) |
| `W` | Warning | `W292` (no newline at EOF), `W293` (blank line with whitespace) |
| `F` | Pyflakes | `F401` (unused import), `F541` (f-string without placeholders), `F821` (undefined name) |

Formatting rules (`RUF`, `I`, `Q`, etc.) and naming conventions (`N`) are intentionally excluded because they overlap with opinionated LLM feedback. For example, `N806` (variable in function should be lowercase) might conflict with the LLM's assessment of whether a variable name is acceptable in context.

### Case-Insensitive Deduplication

Deduplication is case-insensitive because Ruff and the LLM may produce the same finding with different casing. For example, Ruff outputs `"W292: No newline at end of file"` while the LLM might produce `"W292: no newline at end of file"`. Without case-insensitive matching, both would appear in the output as duplicate findings.

### Trade-off: AGENT_STYLE vs Category.STYLE

The `agent_name` field (`"style"`) originates from the `AGENT_STYLE` constant and is stamped by `BaseAnalysisAgent.run()`. The `category` field (`Category.STYLE`) is set inside `StyleAgent.analyze()`. These are intentionally **decoupled**:

- `agent_name` tells you **which agent** produced the finding (for routing, deduplication, dashboard filtering).
- `category` tells you **what kind** of issue it is (for grouping, severity assignment, fix prioritization).

In practice, for the style agent, both are always `"style"` / `Category.STYLE`. But the decoupling allows future flexibility — e.g., the security agent might produce a `Category.STYLE` finding if it detects a security-relevant naming anti-pattern.

### Non-Python Files: Ruff Skipped, LLM Runs

For non-Python files, Ruff is skipped but the LLM still runs. This means the LLM provides style review for JavaScript, TypeScript, Go, and other supported languages — without Ruff hints. The lack of Ruff guidance for non-Python files is an acceptable trade-off: Ruff is Python-only, and the LLM's general code review capabilities apply across languages.

### The `--stdin-filename` Bug

A significant bug was discovered and fixed during the creation of unit and integration tests for the style agent. The original `_run_ruff()` invocation omitted `--stdin-filename` and the trailing `-` (stdin indicator):

```python
# BEFORE (broken): ruff scanned the project directory, not stdin
["ruff", "check", "--output-format", "json", "--select", "E,W,F"]

# AFTER (fixed): ruff scans only stdin content with correct filename
["ruff", "check", "--output-format", "json", "--select", "E,W,F",
 "--stdin-filename", file_path, "-"]
```

Without `--stdin-filename`, Ruff fell back to scanning the entire project directory, producing 116 findings from random project files — all misattributed to the file under review. This bug was invisible in casual testing (Ruff was installed, findings appeared, everything "worked") and was only caught by integration tests that asserted Ruff findings reference symbols actually present in the input code.

---

> **Next Steps for Evaluators:** See `docs/HLD.md` for the full system architecture, `docs/LLD.md` for component-level design details, `docs/project-details/security-agent-architecture.md` for the security agent counterpart, and `docs/USER_FLOWS.md` for end-to-end user journeys. Unit test coverage is in `tests/unit/style-agent/` (42 tests, 0.10s), integration tests in `tests/integration/test_style_agent.py` (8 tests, requires LLM).
