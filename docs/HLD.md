# High-Level Design (HLD)

## System Overview

**Cap PR Review** is an AI-powered multi-agent system that automatically analyzes GitHub pull requests, identifies issues (security, bugs, style, performance), and auto-commits fixes directly to the PR head branch.

### Core Architecture

```
GitHub Enterprise (API)
       ↓
  [FastAPI Service]
       ↓
  [LangGraph Orchestrator]
       ├─ SecurityAgent (RAG + LLM)
       ├─ BugDetectionAgent (AST + LLM)
       ├─ StyleAgent (Ruff + LLM)
       ├─ PerformanceAgent (AST + LLM)
       ├─ FixAgent (commit via GitHub API)
       └─ TestPRAgent (returns PR URL)
       ↓
  [ChromaDB] (OWASP knowledge)
  [Redis/ARQ] (background jobs)
       ↓
  [React Dashboard] (SSE real-time updates)
```

### Key Decisions

1. **Fan-out/Fan-in Parallelism**: The 4 analysis agents (security, bug, style, performance) run in parallel via LangGraph. Results converge at a sync point before fix application.

2. **No Local Git Clone**: All Git operations go through the GitHub REST API (blob POST, tree POST, commit POST, ref PATCH), avoiding the overhead of local cloning.

3. **One Commit Per Category**: Fixes are grouped by category (security → bug → style → performance) and committed separately, for clarity and atomic rollback if needed.

4. **RAG with Graceful Fallback**: Security analysis retrieves OWASP/CWE context from ChromaDB. If ChromaDB is unavailable, a hardcoded knowledge base ensures the agent still works.

5. **Real-time Progress via SSE**: The React dashboard streams review progress (status updates, findings) via Server-Sent Events, creating a live-updating experience.

6. **In-Process MVP**: The review pipeline runs as an `asyncio.create_task()` in the API process. Production would enqueue to Redis/ARQ for durability.

---

## Component Breakdown

### 1. API Layer (FastAPI)

**Responsibilities:**
- Accept PR review requests (manual or webhook)
- Serve review status and findings
- Stream progress via SSE

**Key Routes:**
- `POST /api/v1/reviews` → Create review (202 Accepted)
- `GET /api/v1/reviews` → List reviews (paginated)
- `GET /api/v1/reviews/{id}` → Get review details + findings
- `GET /api/v1/sse/reviews/{id}` → SSE stream
- `POST /api/v1/webhook/github` → GitHub webhook (HMAC verified)

**Middleware:**
- Correlation ID (X-Correlation-ID)
- Rate limiting (60 req/min sliding window)
- HMAC auth (GitHub webhook signature validation)

---

### 2. LangGraph Orchestrator

**Node Graph:**
```
initialize → fetch_pr → check_success
                           ↓
           ┌───────────────┼───────────────┐
           ↓               ↓               ↓ (parallel)
        security         bug            style/perf
           ↓               ↓               ↓
           └───────────────┼───────────────┘
                 aggregate_findings
                           ↓
                  should_apply_fixes
                    ↓             ↓
              (found findings) (no findings)
                    ↓             ↓
                apply_fixes  test_pr
                    ↓             ↓
                 test_pr → finalize → END
```

**State Management:**
- `PRReviewState` TypedDict with Annotated reducers (parallel writes)
- `findings` list accumulates from all agents
- `agent_results` dict merges per-agent outcomes

---

### 3. Analysis Agents

Each agent extends `BaseAnalysisAgent` and implements `analyze(code, file_path) → list[Finding]`.

**SecurityAgent:**
- Queries ChromaDB for top-5 OWASP/CWE docs
- Sends code + context to Claude
- Returns security findings with CWE IDs

**BugDetectionAgent:**
- Runs Python AST analyzers (syntax, semantic, runtime)
- Sends static findings as hints to Claude
- Merges static + LLM findings

**StyleAgent:**
- Runs Ruff linter (if available)
- Asks Claude for additional readability issues
- Dedupes Ruff duplicates from LLM response

**PerformanceAgent:**
- Runs Python AST analyzers (complexity, memory leaks, hotspots)
- Sends hints to Claude
- Returns performance findings

**FixAgent:**
- Filters findings for critical/high/medium (not low/info)
- Groups by category, limits to 10 files/category
- Uses Claude to generate fixed code
- Validates Python syntax with `compile()`
- Commits per category via GitHub REST API
- Updates in-memory files dict for next category

---

### 4. Services

**LLMService**
- Wraps `langchain_anthropic.ChatAnthropic`
- Temperature=0, max_tokens configurable
- Robust `_extract_json()` (fenced code, fallbacks)

**GitHubService**
- Async httpx client for GitHub REST API
- Fetches PR metadata, changed files, file content
- Base URL defaults to `api.github.com` (configurable for Enterprise)

**GitService**
- REST-based commit flow (no local clone)
- Base64-encodes blobs
- GENAI=YES in commit messages

---

### 5. Infrastructure

**ChromaDB**
- Embedded `PersistentClient` (default) or HTTP server
- Stores OWASP top-10 + CWE mapping documents
- Optional `sentence-transformers` embeddings

**Redis/ARQ**
- Job queue for background reviews (future)
- Currently MVP runs in-process

---

### 6. React Dashboard

**Pages:**
- Dashboard: list of reviews
- ReviewDetail: real-time findings table + SSE stream
- TriggerReview: input PR URL, submit, redirect to detail

**Key UX:**
- Live updates via SSE (status, findings appear as they're discovered)
- Grouped findings by category
- Severity badges, confidence indicators

---

## Data Flow

### Trigger → Result

1. **Manual**: User posts PR URL to `/api/v1/reviews`
2. **Webhook**: GitHub sends `pull_request` event to `/api/v1/webhook/github`
3. **Async Run**: `asyncio.create_task(_run_review)` launches pipeline
4. **Fetch PR**: `GitHubService.fetch_pr_data()` downloads PR metadata + changed files
5. **Parallel Analysis**: LangGraph invokes 4 agents in parallel
6. **Aggregation**: Results merge via Annotated reducers
7. **Fix**: FixAgent commits per category (if findings ≥ medium severity)
8. **Stream**: SSE publishes status updates + final findings
9. **Complete**: Review marked as COMPLETED, SSE stream closes

---

## Security & Reliability

- **HMAC Validation**: GitHub webhooks verified with `x-hub-signature-256`
- **Rate Limiting**: 60 requests/min sliding window per client IP
- **No Credentials in Code**: All secrets (API keys, tokens, etc.) from `.env`
- **SSL/TLS**: Optional custom CA bundle for enterprise gateways
- **Graceful Degradation**: RAG unavailable → fallback hardcoded knowledge
- **Per-File Try/Except**: One file's failure doesn't halt the agent
- **Syntax Validation**: Fixed Python code validated with `compile()`

---

## Deployment Notes

- **Backend**: `python -m uvicorn src.main:app --host 0.0.0.0 --port 8000`
- **Worker** (future): `.venv/bin/arq src.worker.WorkerSettings`
- **Redis**: Docker Compose (`docker compose up redis`)
- **Frontend**: `npm run dev` (proxies `/api` → `:8000`)

---

## Performance Characteristics

- **Typical review time**: 30–60 seconds (depends on PR size + LLM latency)
- **Parallelism**: 4 agents in parallel reduce time by ~75% vs. serial
- **Concurrency**: FastAPI + asyncio handles 100s of concurrent review requests
- **ChromaDB**: Embedded mode has ~10ms query latency; HTTP mode adds network cost
