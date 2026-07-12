# Performance Agent

**Path:** `src/agents/performance/`

Hybrid agent combining Python AST static analysis with LLM review to detect performance issues. Part of the fan-out/fan-in analysis pipeline in the multi-agent PR review system.

## Architecture

```
┌──────────────────────────────┐
│  PerformanceAgent.analyze()  │
└─────────────┬────────────────┘
              │
     ┌────────┴────────┐
     │ file is .py?    │
     │ Yes → AST scan  │
     │ No  → skip AST  │
     └────────┬────────┘
              │
     ┌────────┴──────────────────────────────────┐
     │  Static analyzers (run_all)               │
     │  ├── complexity.py (nested loops, length) │
     │  ├── memory_leaks.py (unbounded growth)   │
     │  └── hotspots.py (+= in loop, recompute)  │
     └────────┬──────────────────────────────────┘
              │ static_findings (list[Finding])
              ▼
     ┌────────────────┐    ┌──────────────────┐
     │ performance.j2  │───▶│  LLM             │
     │ (Jinja2 prompt) │    │  (Claude/DeepSeek)│
     └────────────────┘    └────────┬─────────┘
                                    │
              ┌─────────────────────┘
              ▼
     ┌────────────────────────┐
     │ static_findings         │
     │  + llm_findings         │
     │  = final result         │
     └────────────────────────┘
```

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Package marker |
| `agent.py` | `PerformanceAgent` class — runs AST analyzers for Python files, merges static + LLM findings |
| `analyzers/__init__.py` | `run_all()` — dispatches to all three analyzers |
| `analyzers/complexity.py` | Detects nested loops (depth ≥2) and overly long functions (>80 lines) |
| `analyzers/memory_leaks.py` | Detects unbounded container growth inside loops (list/dict/set with append/extend/add) |
| `analyzers/hotspots.py` | Detects `+=` concatenation in loops, and `sorted()`/`len()` recomputed in loop conditions |

## How it works

### 1. Entry point: `PerformanceAgent.analyze(code, file_path)`

Called by `BaseAnalysisAgent.run()` for each source file. The agent takes a dual approach:

### 2. Static analysis (Python-only): `run_all(code, file_path)`

Only runs if `file_path` ends with `.py`. Three analyzers scan the AST:

| Analyzer | What it detects | Severity |
|---|---|---|
| **complexity.py** | Nested loops (depth ≥2: `MEDIUM`, ≥3: `HIGH`), functions >80 lines (`LOW`) | MEDIUM/HIGH/LOW |
| **memory_leaks.py** | Unbounded container growth: `append`/`extend`/`add`/`update`/`insert` on module-level lists inside loops (`HIGH`), local containers inside loops (`MEDIUM`) | HIGH/MEDIUM/LOW |
| **hotspots.py** | `+=` string/list concatenation in loops, `sorted()`/`len()`/`list()` recomputed in loop conditions | MEDIUM |

All analyzers use `src/agents/ast_utils.py` for shared utilities (`parse()`, `attach_parents()`, `loop_depth()`, `is_inside_loop()`).

### 3. Static findings as LLM hints

Static findings are converted to hints (`start_line` + `title`) and passed into the prompt. The LLM uses them as starting points, not as final results — it independently validates and expands on them.

### 4. Prompt rendering: `performance.j2`

Jinja2 template at `src/prompts/templates/performance.j2`:

- Sets role: "performance engineer"
- **SCOPE**: inefficient algorithms (O(n²)), N+1 queries, repeated work in loops, unbounded memory growth/leaks, blocking I/O in async code, obvious hotspots
- Explicitly excludes: security, bugs, style, general code quality
- Injects static finding hints (line + title) above the code
- Includes `_common.j2` — JSON output contract

### 5. LLM call + merge

- LLM call via `LLMService.complete_json()` with temperature=0
- Response parsed via `findings_from_llm()` → `list[Finding]`
- **Final result**: `static_findings + llm_findings` — both static and LLM findings are returned. The LLM may validate, reject, or add to the static hints.

### 6. Non-Python files

If the file isn't `.py`, the AST analyzers are skipped entirely. Only the LLM cCall is made. This means performance analysis for Java, JS, Go, etc. relies on LLM alone.

## Dependencies

| Dependency | Used for | Optional? |
|---|---|---|
| `src.services.llm_service.LLMService` | LLM completion | No |
| `src.agents.parsing` | JSON → Finding conversion | No |
| `src.agents.ast_utils` | `parse()`, `attach_parents()`, `loop_depth()`, `is_inside_loop()` | Yes — only for Python files |
| `src.agents.base.BaseAnalysisAgent` | Per-file iteration, error isolation | No |

## Configuration

Same as SecurityAgent — uses the shared LLM configuration (`LLM_API_KEY`, `LLM_BASE_URL`, `PRIMARY_MODEL`, `LLM_MAX_TOKENS`).

## Testing

| Layer | Location | Status |
|---|---|---|
| **Unit** | `tests/unit/` | Not yet implemented |
| **Integration** | `tests/integration/` | Not yet implemented |

### Suggested test plan

```bash
# Unit: Test individual analyzers with known AST patterns
# e.g., nested loops → 1 finding, += in loop → 1 finding, clean code → 0 findings

# Integration: Run full agent against known performance-issue code with real LLM
uv run pytest tests/integration/test_performance_agent.py -v -s
```

## Known limitations

- **Python-only static analysis**: AST analyzers only work on `.py` files. Java, JS, Go, etc. rely entirely on the LLM.
- **Heuristic memory-leak detection**: The unbounded-container check is a heuristic — it flags patterns like `global_list.append(x)` in a loop, but can't trace if the list is bounded elsewhere.
- **No cross-file analysis**: Like all agents, each file is analyzed in isolation.
- **No profiling data**: Static analysis can't measure actual runtime — only identify patterns that commonly cause issues.
