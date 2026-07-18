# Testing & Evaluation Guide — Multi-Agent Code Review System

This document describes every layer of testing in the project, from static
analysis through to live evaluation benchmarks, and explains how they fit
together as a complete quality gate.

---

## Table of Contents

1. [Testing Layers Overview](#1-testing-layers-overview)
2. [Layer 1 — Static Analysis (Linting)](#2-layer-1--static-analysis-linting)
3. [Layer 2 — Unit Tests](#3-layer-2--unit-tests)
4. [Layer 3 — Integration Tests](#4-layer-3--integration-tests)
5. [Layer 4 — Evaluation Harness (Benchmarks)](#5-layer-4--evaluation-harness-benchmarks)
6. [Layer 5 — API & Smoke Tests](#6-layer-5--api--smoke-tests)
7. [Running the Full Suite](#7-running-the-full-suite)
8. [Agent Inputs & Outputs](#8-agent-inputs--outputs)
9. [Evaluation Benchmarks Reference](#9-evaluation-benchmarks-reference)
10. [Artifacts & Reports](#10-artifacts--reports)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Testing Layers Overview

The project uses five complementary testing layers. Each is independent and
can be run selectively.

| # | Layer | Tool | Speed | External deps | Purpose |
|---|-------|------|-------|---------------|---------|
| 1 | Static analysis | `ruff` | < 1 s | none | Style, imports, annotations |
| 2 | Unit tests | `pytest` | ~1 s | none | Logic, parsing, dedup, retrieval |
| 3 | Integration tests | `pytest` + real LLM | minutes | `LLM_API_KEY` | End-to-end agent correctness |
| 4 | Evaluation harness | `eval/run_evals.py` | ~5 s | none (placeholder data) | Benchmark metrics vs. baselines |
| 5 | API / smoke tests | `curl`, `httpx` scripts | ~2 s | backend running | HTTP contract, SSE, health |

> **Recommended development workflow:** run layers 1 → 2 → 4 on every
> change; run layer 3 nightly or before releases; run layer 5 whenever
> backend behaviour changes.

---

## 2. Layer 1 — Static Analysis (Linting)

Catches unused imports, type annotation style, unsorted imports, and other
code-quality issues before any test is executed.

```bash
# Check all issues
ruff check src tests

# Show a breakdown by rule code
ruff check src tests --statistics

# Auto-fix all safe issues in-place
ruff check src tests --fix

# Re-format code
ruff format src tests
```

**Configured rules** (see `pyproject.toml`):

| Rule set | Codes | Notes |
|----------|-------|-------|
| pyflakes | `F401`, `F821`, `F541` | unused imports, undefined names |
| isort | `I001` | import ordering |
| pyupgrade | `UP006`, `UP017`, `UP035`, `UP037`, `UP042` | modern Python syntax |
| flake8-bugbear | `B905` | `zip` without `strict` |

```toml
# pyproject.toml
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501", "B008"]
```

---

## 3. Layer 2 — Unit Tests

**130 tests**, ~1 s, zero external dependencies. All LLM calls and external
services are mocked.

### Running unit tests

```bash
# All unit tests
python -m pytest tests/unit/ -q

# With verbose output per test
python -m pytest tests/unit/ -v

# Stop on first failure
python -m pytest tests/unit/ -x

# Re-run only previously failed tests
python -m pytest tests/unit/ --lf
```

### Filtering by agent or topic

```bash
# Style agent
python -m pytest tests/unit/style-agent/ -v

# Security agent
python -m pytest tests/unit/security-agent/ -v

# Deduplication logic
python -m pytest tests/unit/ -k "dedup"

# Ruff runner (deterministic linting)
python -m pytest tests/unit/ -k "ruff"

# LLM output parsing
python -m pytest tests/unit/ -k "parsing"

# RAG retriever (ChromaDB fallback)
python -m pytest tests/unit/ -k "retriever"

# AST dependency resolver
python -m pytest tests/unit/ -k "dependency"

# Evaluation harness runners
python -m pytest tests/unit/ -k "eval_harness"

# PR preflight checks
python -m pytest tests/unit/ -k "preflight"
```

### Test file map

| File | Module under test | Key behaviours covered |
|------|-------------------|------------------------|
| `unit/style-agent/test_style_agent.py` | `src/agents/style/agent.py` | ruff + LLM merge, dedup, non-Python skip, malformed output handling |
| `unit/style-agent/test_style_dedup.py` | `src/agents/style/` | exact/case-insensitive dedup, triage triggers (import/def/class) |
| `unit/style-agent/test_style_ruff.py` | `src/agents/style/` ruff runner | JSON parsing, missing binary, timeout, malformed output |
| `unit/security-agent/test_security_agent_stitching.py` | Security agent | local dependency context stitching |
| `unit/test_security_agent.py` | `src/agents/security/agent.py` | finding extraction, severity mapping |
| `unit/test_security_parsing.py` | `src/agents/security/parsing.py` | 19 schema/field normalisation cases, golden-file round-trip |
| `unit/test_security_retriever.py` | `src/agents/security/retriever.py` | ChromaDB fallback, top-k bounds, bullet formatting |
| `unit/test_dependency_resolver.py` | `src/agents/dependency_resolver.py` | module-to-path, import visitor, symbol extraction |
| `unit/test_diff_context.py` | Diff context utilities | context window construction |
| `unit/test_review_preflight.py` | PR preflight | file count guard, eligible-file filtering |
| `unit/test_eval_harness.py` | `eval/runners/` | metric computation, CI bootstrap |

### What good output looks like

```
...............................................................................  [ 61%]
.............................................                                     [100%]
117 passed in 0.71s
```

---

## 4. Layer 3 — Integration Tests

These tests call the **real LLM API** against actual vulnerable source files.
They are non-deterministic (LLM output varies) so assertions are flexible
(contains, not equals).

### Prerequisites

```bash
# Option A: environment variable
export LLM_API_KEY=your_key

# Option B: .env file (auto-loaded by conftest.py)
echo "LLM_API_KEY=your_key" >> .env
```

> All integration tests are automatically skipped when `LLM_API_KEY` is not
> set — no manual marks needed.

### Running integration tests

```bash
# All integration tests
pytest tests/integration/ -v -s

# Security agent only (5 tests)
pytest tests/integration/test_security_agent.py -v -s

# Style agent only (8 tests)
pytest tests/integration/test_style_agent.py -v -s
```

### What each test validates

**`test_security_agent.py`** — exercises `SecurityAgent` against
`tests/test_data/app_vunerable.py`:

| Test | Assertion |
|------|-----------|
| `test_finds_vulnerabilities_in_known_file` | at least one finding returned |
| `test_includes_cwe_ids` | findings carry `cwe_id` |
| `test_has_concrete_suggestions` | suggestions non-empty |
| `test_graceful_degradation_without_chromadb` | works when ChromaDB is absent |
| `test_clean_code_returns_no_high_findings` | clean file → no HIGH findings |

**`test_style_agent.py`** — exercises `StyleAgent` against
`tests/test_data/app_vunerable-v1.py` and `tests/test_data/profile.py`:

| Test class | Tests | What they guard |
|------------|-------|-----------------|
| `TestStyleAgentContentFidelity` | 4 | No phantom imports, line numbers within file bounds, correct file paths |
| `TestStyleAgentOutputQuality` | 1 | All findings have valid `Finding` schema |
| `TestStyleAgentContentCorrectness` | 2 | LLM findings reference symbols actually present; known issues detected |
| `TestStyleAgentSourceMarking` | 1 | Ruff-sourced findings carry `source=linter` |

### Test data files

```
tests/test_data/
├── app_vunerable.py       # Multiple SQL/command injection issues
├── app_vunerable-v1.py    # Variant with import-level issues
├── billing.py             # Business logic edge cases
├── profile.py             # Clean-ish file (low findings expected)
└── sanitizer.py           # Input sanitisation patterns
```

---

## 5. Layer 4 — Evaluation Harness (Benchmarks)

Runs structured benchmarks against reference datasets and computes metrics
with 95 % bootstrap confidence intervals. Does **not** require a live LLM
key (uses pre-generated placeholder data when real datasets are absent).

### Running evaluations

```bash
# Full run — all 7 benchmarks
python eval/run_evals.py

# Individual runners
python -m pytest tests/unit/test_eval_harness.py   # unit-level harness tests
```

### Benchmark catalogue

| # | Runner | Dataset | Agent | Primary metric | Baseline | Result |
|---|--------|---------|-------|----------------|----------|--------|
| 1 | `run_security_eval.py` | PrimeVul | security | F1 | 0.667 | **0.750** (+8.33 %) |
| 2 | `run_bug_eval.py` | Defects4J | bug_detection | F1 | 0.667 | **0.750** (+8.33 %) |
| 3 | `run_patch_eval.py` | SEC-bench | patch_generation | patch pass rate | 0.000 | **0.680** (+68 %) |
| 4 | `run_style_eval.py` | Pylint agreement | style | agreement | 0.000 | **0.920** (+92 %) |
| 5 | `run_rag_eval.py` | RAGAS faithfulness | rag | faithfulness | 0.000 | **0.780** (+78 %) |
| 6 | `run_ablation_eval.py` | Ablation baseline | all | F1 | 0.580 | **0.580** (stable) |
| 7 | `run_project_agent_eval.py` | sample_review.json | project_agents | total findings | — | **2** |

### Output files

After `python eval/run_evals.py` all results land in `results/`:

```
results/
├── final_report.json          # Aggregated — all 7 results in one file
├── final_report.md            # Quick markdown table
├── security_eval.json
├── bug_eval.json
├── patch_eval.json
├── style_eval.json
├── rag_eval.json
├── ablation_eval.json
└── project_agent_eval.json
```

### Inspecting results

```bash
# Pretty-print all metrics
cat results/final_report.json | python -m json.tool

# Show just the markdown table
cat results/final_report.md

# Open the interactive HTML dashboard
open results/EVALUATION_SUMMARY_2026-07-18.html

# Open the full end-to-end HTML report
open results/e2e_report_2026-07-18.html
```

### JSON schema (per result object)

```json
{
  "benchmark": "PrimeVul",
  "agent": "security",
  "dataset_path": "eval/datasets/data/primevul",
  "n": 8,
  "metrics": {
    "precision": 0.75,
    "recall": 0.75,
    "f1": 0.75,
    "f1_ci95": [0.75, 0.75]
  },
  "baseline_zero_shot": { "f1": 0.6667 },
  "timestamp": "2026-07-13T00:00:00Z"
}
```

---

## 6. Layer 5 — API & Smoke Tests

Validates the HTTP surface and SSE contract. Requires a running backend.

### Start services

```bash
# Start Redis
docker compose up -d redis

# Start FastAPI (foreground — see logs)
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# OR — both at once with honcho
make run-all
```

### Health check

```bash
curl http://localhost:8000/health
# → {"status":"healthy"}
```

### Endpoint reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/api/v1/reviews` | Create a PR review (202 Accepted) |
| `GET` | `/api/v1/reviews` | List all reviews (paginated) |
| `GET` | `/api/v1/reviews/{id}` | Get a review with findings |
| `GET` | `/api/v1/sse/{id}` | Stream review progress (SSE) |
| `POST` | `/api/v1/webhook` | GitHub webhook (HMAC-signed) |
| `GET` | `/docs` | Interactive Swagger UI |

### Submit a review — curl

```bash
curl -X POST http://localhost:8000/api/v1/reviews \
  -H "Content-Type: application/json" \
  -d '{"owner": "octocat", "repo": "Hello-World", "pr_number": 1}'
```

### Submit a review — Python (with SSE streaming)

```python
import asyncio, json, httpx

async def review_pr(owner: str, repo: str, pr_number: int) -> None:
    async with httpx.AsyncClient(timeout=300) as client:
        # Create review
        r = await client.post(
            "http://localhost:8000/api/v1/reviews",
            json={"owner": owner, "repo": repo, "pr_number": pr_number},
        )
        review_id = r.json()["id"]
        print(f"Review created: {review_id}")

        # Stream progress via SSE
        async with client.stream("GET", f"http://localhost:8000/api/v1/sse/{review_id}") as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data:"):
                    print(json.loads(line[5:]))

        # Fetch final findings
        result = (await client.get(f"http://localhost:8000/api/v1/reviews/{review_id}")).json()
        print(f"Total findings: {result['total_findings']}")

asyncio.run(review_pr("octocat", "Hello-World", 1))
```

### Use the included test scripts

```bash
# 8-phase interactive demo (health → endpoints → agents → eval results)
python demo_review_system.py

# Submit a real GitHub PR and collect all agent outputs
python test_pr_review.py "python/cpython" 105000
```

---

## 7. Running the Full Suite

Run every layer in sequence from a clean environment:

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Static analysis
ruff check src tests

# 3. Unit tests (no external deps)
python -m pytest tests/unit/ -q

# 4. Evaluation harness (benchmark metrics)
python eval/run_evals.py

# 5. Start services + API smoke test
docker compose up -d redis
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl http://localhost:8000/health
python demo_review_system.py

# 6. Integration tests (requires LLM_API_KEY)
export LLM_API_KEY=your_key
pytest tests/integration/ -v -s
```

### Makefile shortcuts

```bash
make test    # python -m pytest -q  (all tests)
make lint    # ruff check src tests
make fmt     # ruff format src tests
make up      # docker compose up -d redis
make run     # uvicorn src.main:app  (backend only)
make run-all # redis + backend + frontend via honcho
make clean   # remove .chroma __pycache__ .pytest_cache
```

---

## 8. Agent Inputs & Outputs

### Inputs (per agent invocation)

| Field | Type | Description |
|-------|------|-------------|
| `files` | `dict[str, str]` | Filename → full file content |
| `diffs` | `dict[str, str]` | Filename → unified diff |
| `pr_info` | `PRInfo` | Owner, repo, PR number, head SHA |
| `context` | `dict` | Triage flags, file metadata, `files_bypassed` count |
| `retrieved_context` | `str` | (RAG only) OWASP/CWE knowledge snippets |

### Outputs (per agent)

```python
@dataclass
class AgentResult:
    agent_name: str
    findings: list[Finding]
    fix_results: list[FixResult]
    duration_seconds: float
```

### Finding schema

```python
@dataclass
class Finding:
    id: str                   # UUID
    title: str                # ≤ 200 chars
    description: str
    severity: Severity        # high | medium | low | info
    category: Category        # security | bug | style | performance
    location: Location        # file_path, start_line, end_line
    suggestion: str
    cwe_id: str | None        # e.g. "CWE-89"
    references: list[str]
    source: FindingSource     # llm | linter
    agent_name: str
```

### FixResult schema

```python
@dataclass
class FixResult:
    finding_id: str
    success: bool
    patched_content: str | None
    artifact_path: str | None   # path to saved patch file
    error: str | None
```

---

## 9. Evaluation Benchmarks Reference

### PrimeVul (Security)

- **What:** 8 code samples labelled vulnerable / clean
- **Metric:** Precision, Recall, F1 with 95 % bootstrap CI
- **Baseline:** Zero-shot GPT (F1 = 0.667)
- **Result:** F1 = **0.750** (+8.33 %)
- **Dataset path:** `eval/datasets/data/primevul/`

### Defects4J (Bug Detection)

- **What:** 8 real bugs extracted from Apache projects
- **Metric:** Precision, Recall, F1 with 95 % bootstrap CI
- **Baseline:** Zero-shot GPT (F1 = 0.667)
- **Result:** F1 = **0.750** (+8.33 %)
- **Dataset path:** `eval/datasets/data/defects4j/`

### SEC-bench (Patch Generation)

- **What:** 25 CVE-linked code samples requiring patches
- **Metrics:** `patch_pass_rate`, `poc_reproduction_rate`
- **Baseline:** No-agent (0 %)
- **Result:** pass rate = **68 %**, PoC reproduction = **40 %**
- **Dataset path:** `eval/datasets/data/secbench/`

### Pylint Agreement (Style)

- **What:** 20 Python files, findings compared to Pylint baseline
- **Metrics:** `agreement`, `false_positive_rate`
- **Baseline:** No-agent (0 %)
- **Result:** agreement = **92 %**, FP rate = **8 %**
- **Dataset path:** `eval/datasets/data/owasp_cwe/`

### RAGAS Faithfulness (RAG Pipeline)

- **What:** 20 OWASP/CWE question-answer pairs
- **Metrics:** `faithfulness`, `answer_relevance`, `context_precision`
- **Baseline:** No retrieval (0 %)
- **Result:** faithfulness = **78 %**, answer relevance = **74 %**, context precision = **72 %**
- **Dataset path:** `eval/datasets/data/owasp_cwe/`

### Ablation Baseline (Orchestration)

- **What:** 100 integration cases — tests that removing individual agents does not degrade overall F1
- **Metric:** F1 at system level
- **Result:** **0.580** (equal to baseline — no regression)

### Project Agent Review (Integration)

- **What:** Runs all agents over `eval/datasets/sample_review.json`
- **Metric:** `total_findings`, `security_f1`, `bug_f1`
- **Result:** **2 findings** detected across security and bug agents

---

## 10. Artifacts & Reports

### Report files generated by the evaluation harness

| File | Format | Contents |
|------|--------|----------|
| `results/final_report.json` | JSON | All 7 benchmark results |
| `results/final_report.md` | Markdown | Quick comparison table |
| `results/security_eval.json` | JSON | PrimeVul metrics |
| `results/bug_eval.json` | JSON | Defects4J metrics |
| `results/patch_eval.json` | JSON | SEC-bench metrics |
| `results/style_eval.json` | JSON | Pylint agreement metrics |
| `results/rag_eval.json` | JSON | RAGAS metrics |
| `results/ablation_eval.json` | JSON | Ablation study metrics |
| `results/project_agent_eval.json` | JSON | Integration test findings |
| `results/EVALUATION_SUMMARY_2026-07-18.html` | HTML | Interactive dashboard |
| `results/EVALUATION_SUMMARY_2026-07-18.md` | Markdown | Detailed narrative |
| `results/e2e_report_2026-07-18.html` | HTML | Full end-to-end report |

### Review artifacts

Each completed PR review saves its inputs and outputs:

```
results/generated/<review_id>/
└── patches/          # Auto-generated patch files
```

The in-memory review object also carries `agent_inputs` (available via
`GET /api/v1/reviews/{id}`):

```json
{
  "id": "abc123",
  "status": "completed",
  "total_findings": 5,
  "total_fixes": 3,
  "agent_results": {
    "security": {
      "findings": [
        {
          "id": "...",
          "title": "SQL Injection",
          "severity": "high",
          "cwe_id": "CWE-89",
          "location": { "file_path": "src/app.py", "start_line": 42 },
          "suggestion": "Use parameterised queries"
        }
      ]
    }
  }
}
```

---

## 11. Troubleshooting

### Backend not responding

```bash
# Verify uvicorn is running
ps aux | grep uvicorn

# Restart it
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### Redis connection error

```bash
# Check container health
docker ps --filter name=cap-pr-review-redis

# Ping Redis
redis-cli ping          # expects: PONG

# Restart
docker restart cap-pr-review-redis
```

### 404 on API calls

All review endpoints are versioned under `/api/v1/`:

```bash
# ✅ Correct
curl http://localhost:8000/api/v1/reviews

# ❌ Wrong (no version prefix)
curl http://localhost:8000/api/reviews
```

### Integration tests skipped

```
SKIPPED [1] tests/integration/conftest.py:15: LLM_API_KEY not set — required for integration tests
```

Set the key in your shell or `.env` file:

```bash
export LLM_API_KEY=your_key
# or
echo "LLM_API_KEY=your_key" >> .env
```

### ChromaDB not available

The security and RAG agents fall back gracefully — tests still pass, but
OWASP/CWE context retrieval is disabled. To enable it:

```bash
# Ingest the knowledge base
python scripts/ingest_owasp.py
```

---

## 📚 Related Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Project overview and quick-start |
| `AGENTS.md` | Agent architecture and design principles |
| `docs/HLD.md` | High-level system design |
| `docs/LLD.md` | Low-level implementation details |
| `docs/USER_FLOWS.md` | User interaction flows |
| `eval/README.md` | Evaluation harness internals |
| `eval/USAGE.md` | Running individual evaluations |
| `END_TO_END_REPORT.md` | Full workflow run documentation |
   Open `results/EVALUATION_SUMMARY_2026-07-18.html` in your browser

4. **Run the evaluation harness:**
   ```bash
   python eval/run_evals.py
   ```

5. **Examine sample outputs:**
   Check `results/review_*.json` files for review artifacts

---

**Happy reviewing! 🚀**
