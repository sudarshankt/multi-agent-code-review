# Style Agent

**Path:** `src/agents/style/`

Hybrid agent combining Ruff linter (if available) with LLM review for code readability and maintainability. Part of the fan-out/fan-in analysis pipeline in the multi-agent PR review system.

## Architecture

```
┌──────────────────────────┐
│  StyleAgent.analyze()    │
└─────────────┬────────────┘
              │
     ┌────────┴────────┐
     │ file is .py?    │
     │ Yes → run Ruff  │
     │ No  → skip Ruff │
     └────────┬────────┘
              │
              ▼
     ┌────────────────────┐
     │  _run_ruff()        │
     │  subprocess: `ruff  │
     │  check --select     │
     │  E,W,F --format json│
     └────────┬───────────┘
              │ ruff_findings (list[Finding])
              ▼
     ┌────────────────┐    ┌──────────────────┐
     │  style.j2       │───▶│  LLM             │
     │ (Jinja2 prompt) │    │  (Claude/DeepSeek)│
     └────────────────┘    └────────┬─────────┘
                                    │ llm_findings
              ┌─────────────────────┘
              ▼
     ┌────────────────────────┐
     │ Deduplication:          │
     │ remove LLM findings     │
     │ whose title matches     │
     │ a Ruff finding (case-   │
     │ insensitive)            │
     └────────┬───────────────┘
              ▼
     ┌────────────────────────┐
     │ ruff_findings            │
     │  + deduped_llm_findings  │
     │  = final result          │
     └────────────────────────┘
```

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Package marker |
| `agent.py` | `StyleAgent` class — runs Ruff linter for Python, deduplicates LLM findings against Ruff |

## How it works

### 1. Entry point: `StyleAgent.analyze(code, file_path)`

Called by `BaseAnalysisAgent.run()` for each source file. Uses a two-phase approach: Ruff (deterministic) → LLM (subjective), with deduplication.

### 2. Ruff linter (Python-only): `_run_ruff(code, file_path)`

Only runs if `file_path` ends with `.py`:

- Invokes `ruff check` as a subprocess with `--select E,W,F` and `--output-format json`
- `E` = pycodestyle errors, `W` = pycodestyle warnings, `F` = Pyflakes (unused imports, undefined names)
- Code is piped via stdin (no temp file creation)
- Timeout: 10 seconds
- **Graceful degradation**: if Ruff isn't installed (`FileNotFoundError`) or times out, returns `[]` silently
- Parses the JSON output into `Finding` objects with `severity=LOW` and `source=FindingSource.LINTER`

### 3. Prompt rendering: `style.j2`

Jinja2 template at `src/prompts/templates/style.j2`:

- Sets role: "code reviewer focused on readability and maintainability"
- **SCOPE**: unclear naming, dead code, overly complex functions, missing docstrings, inconsistent style, anti-patterns
- Explicitly excludes: security, bugs, performance, and **Ruff-detected issues** (listed in the prompt so the LLM won't duplicate them)
- Injects Ruff issues as a block above the code: `- L{line} {code}: {title}`
- Includes `_common.j2` — JSON output contract

### 4. LLM call

- Sends the prompt via `LLMService.complete_json()` with temperature=0
- Response parsed via `findings_from_llm()` → `list[Finding]`

### 5. Deduplication

The LLM prompt explicitly lists Ruff findings and says "do NOT duplicate them." As a safety net, the agent also programmatically deduplicates:

```python
ruff_titles = {f.title.lower() for f in ruff_findings}
deduped_llm = [f for f in llm_findings if f.title.lower() not in ruff_titles]
```

Case-insensitive title matching ensures the LLM doesn't re-report what Ruff already caught.

### 6. Final result

`ruff_findings + deduped_llm_findings` — Ruff provides deterministic, zero-cost linting; the LLM adds subjective readability and maintainability observations.

### 7. Non-Python files

If the file isn't `.py`, Ruff is skipped entirely. Only the LLM call is made.

## Dependencies

| Dependency | Used for | Optional? |
|---|---|---|
| `src.services.llm_service.LLMService` | LLM completion | No |
| `src.agents.parsing` | JSON → Finding conversion | No |
| `ruff` (system CLI) | Python style linting | Yes — skipped if unavailable |
| `src.agents.base.BaseAnalysisAgent` | Per-file iteration, error isolation | No |

## Configuration

Same as other agents — uses the shared LLM configuration (`LLM_API_KEY`, `LLM_BASE_URL`, `PRIMARY_MODEL`, `LLM_MAX_TOKENS`).

Ruff uses the project's `pyproject.toml` configuration automatically:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501", "B008"]
```

Note: the agent's `_run_ruff()` explicitly passes `--select E,W,F` which overrides the project config's selection — only basic pycodestyle/Pyflakes rules are checked by the agent, even if the project config has broader rules.

## Testing

| Layer | Location | Status |
|---|---|---|
| **Unit** | `tests/unit/` | Not yet implemented |
| **Integration** | `tests/integration/` | Not yet implemented |

### Suggested test plan

```bash
# Unit: Test _run_ruff() with known code → assert Finding objects with correct codes
# Unit: Test Ruff unavailable → returns []
# Unit: Test deduplication → LLM finding with same title as Ruff finding is removed

# Integration: Run full agent against messy code with real LLM
uv run pytest tests/integration/test_style_agent.py -v -s
```

## Known limitations

- **Ruff override**: Agent passes `--select E,W,F`, overriding the project's `pyproject.toml` selection. Full project rules (`I`, `UP`, `B`) are not checked.
- **Python-only**: Ruff only runs on `.py` files. Style analysis for other languages relies entirely on LLM.
- **No auto-fix**: Ruff is used in check-only mode (`ruff check`). No `--fix` or auto-formatting is applied.
- **Deduplication is title-based**: If the LLM reports the same issue with a slightly different title (e.g., different wording), it won't be deduplicated. The prompt asks the LLM not to duplicate, which is the primary defense; the title match is a safety net.
