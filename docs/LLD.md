# Low-Level Design (LLD)

## Detailed Component Specifications

### 1. Configuration (`src/core/config.py`)

**Settings Class (pydantic-settings)**

Groups environment variables into logical accessors:
- `settings.app` → app_env, version, log_level, log_json
- `settings.api` → host, port, cors_origins, rate_limit_per_minute
- `settings.llm` → primary_model, base_url, api_key, max_tokens, timeout, ssl_cert_file
- `settings.github` → token, base_url, webhook_secret, ca_bundle
- `settings.redis` → host, port, db, dsn
- `settings.chromadb` → mode, host, port, persist_dir, collection
- `settings.langfuse` → enabled, public_key, secret_key, host
- `settings.worker` → max_jobs, job_timeout

**Cached via `@lru_cache`**. Load from `.env` on first call.

---

### 2. Logging (`src/core/logging.py`)

**structlog Configuration**
- Timestamper (ISO UTC)
- Correlation ID via contextvars (propagates across async tasks)
- JSON or console renderer (configurable)
- **IMPORTANT**: Never use `event=` kwarg; use `sse_event=` instead (reserved in structlog)

**ContextVar**: `_correlation_id` set by `CorrelationIDMiddleware`, available in all logs.

---

### 3. Exception Hierarchy (`src/core/exceptions.py`)

Each exception carries `retry_policy: RetryPolicy(backoff, max_attempts)`:

| Exception | Backoff | Max Attempts |
|-----------|---------|--------------|
| GitHubAPIError | exponential | 3 |
| GitHubRateLimitError | linear | 5 |
| LLMError | exponential | 3 |
| LLMRateLimitError | linear | 5 |
| LLMContextLengthError | none | 1 |
| AgentError | exponential | 2 |
| AgentTimeoutError | immediate | 1 |
| RAGError | exponential | 2 |
| GitOperationError | immediate | 2 |
| WebhookValidationError | none | 1 |
| QueueError | exponential | 3 |

**Used by**: Callers can `except` and check `exc.retry_policy.retryable` to decide whether to retry.

---

### 4. Models

**Finding** (`src/models/finding.py`)
```python
class Finding:
    id: str  # uuid4 hex
    category: Category  # security|bug_detection|style|performance
    severity: Severity  # critical|high|medium|low|info
    confidence: Confidence  # high|medium|low
    title: str
    description: str
    location: Location  # file_path, start_line, end_line, snippet
    suggestion: str | None
    references: list[str]
    cwe_id: str | None
    agent_name: str | None  # set by agent
    created_at: datetime
```

**Review** (`src/models/review.py`)
```python
class Review:
    id: str
    pr_info: PRInfo
    status: ReviewStatus  # pending→fetching→analyzing→fixing→testing→completed|failed
    agent_results: dict[str, AgentResult]  # {agent_name: {status, findings, duration, error}}
    total_findings: int
    total_fixes: int
    fix_branch: str | None
    fix_pr_url: str | None
    triggered_by: str  # "api" or "webhook"
    error_message: str | None
    created_at, updated_at, completed_at: datetime
```

---

### 5. LLM Service (`src/services/llm_service.py`)

**LLMService**
- Wraps `ChatAnthropic` from `langchain_anthropic`
- **NO `http_async_client` parameter** (not supported; use env vars for SSL)
- Temperature=0 (deterministic)
- Rate limiter: `InMemoryRateLimiter(requests_per_second)`
- Timeout: 120 seconds

**JSON Extraction (`_extract_json`)**
Priority order:
1. JSON inside markdown fences (\`\`\`json ... \`\`\`)
2. Full text as JSON
3. First balanced `[...]` or `{...}` by order of appearance
4. Empty array `[]` fallback

---

### 6. GitHub Service (`src/services/github_service.py`)

**GitHubService**
- `httpx.AsyncClient` with Bearer token auth
- Base URL: `https://api.github.com` (or configured)
- SSL verify: system trust store, or custom CA bundle

**Methods**:
- `get_pr(owner, repo, pr_number)` → dict (PR metadata)
- `get_pr_files(owner, repo, pr_number)` → list[dict] (paginated)
- `get_file_content(owner, repo, path, ref)` → str | None (base64-decoded)
- `fetch_pr_data(owner, repo, pr_number)` → dict with pr_info + files dict

**File Filtering**: Only source extensions (`SOURCE_EXTENSIONS`) included; removed files excluded.

---

### 7. Git Service (`src/services/git_service.py`)

**Git Commit Flow (no local clone)**

1. `GET /repos/{owner}/{repo}/git/ref/heads/{branch}` → HEAD SHA
2. `GET /repos/{owner}/{repo}/git/commits/{sha}` → base tree SHA
3. For each file:
   - `POST /repos/{owner}/{repo}/git/blobs` with `{"content": base64_str, "encoding": "base64"}` → blob SHA
4. `POST /repos/{owner}/{repo}/git/trees` with `{"base_tree": ..., "tree": [...]}` → new tree SHA
5. `POST /repos/{owner}/{repo}/git/commits` with message (MUST contain "GENAI=YES") → commit SHA
6. `PATCH /repos/{owner}/{repo}/git/refs/heads/{branch}` with new SHA

**Important**: Blobs MUST be base64-encoded. UTF-8 encoding rejected by enterprise pre-receive hooks.

---

### 8. Base Analysis Agent (`src/agents/base.py`)

```python
class BaseAnalysisAgent(ABC):
    name: str
    
    @abstractmethod
    async def analyze(code: str, file_path: str, context: dict) -> list[Finding]:
        """Analyze one file."""
    
    async def run(files: dict[str, str], context: dict) -> list[Finding]:
        """Iterate files (SOURCE_EXTENSIONS), per-file try/except, aggregate findings."""
        # 1. Filter by extension
        # 2. For each file, await analyze()
        # 3. Catch exceptions per file (don't halt agent)
        # 4. Set agent_name on all findings
        # 5. Log duration
```

---

### 9. Agents

**SecurityAgent**
- Retrieves OWASP/CWE context from ChromaDB (top-5)
- Falls back to hardcoded 8-entry fallback if ChromaDB unavailable
- Renders `security.j2` template with code + rag_context
- Parses JSON findings via `findings_from_llm()`

**BugDetectionAgent**
- Runs static analyzers: syntax, semantic, runtime (Python only)
- Renders `bug_detection.j2` with static findings as hints
- Merges static + LLM findings (LLM should avoid obvious static issues)

**StyleAgent**
- Runs Ruff subprocess (if installed) with `--output-format json`
- Renders `style.j2` with code + Ruff issues as hints
- Dedupes LLM findings that duplicate Ruff issues (by title match)

**PerformanceAgent**
- Runs static analyzers: complexity, memory_leaks, hotspots (Python only)
- Renders `performance.j2` with hints
- Merges static + LLM findings

**FixAgent**
- Filters findings for severity in `FIXABLE_SEVERITIES` = (critical, high, medium)
- Groups by `category` (security, bug, style, performance)
- Limits to `MAX_FIX_FILES_PER_CATEGORY` (10) per category
- Per-file: LLM generates fix, validate Python syntax with `compile()`
- Commits per category with message: `[pr-review] GENAI=YES: fix {category} issues`
- Updates in-memory `files` dict between categories (next category fixes prev. category's fixes)

**TestPRAgent**
- Currently stub; returns PR URL (test generation disabled per spec)

---

### 10. Prompt Templates (`src/prompts/templates/`)

All use a shared JSON contract (`_common.j2`):
```json
[
  {
    "title": "...",
    "description": "...",
    "severity": "critical|high|medium|low|info",
    "confidence": "high|medium|low",
    "start_line": <int or null>,
    "end_line": <int or null>,
    "suggestion": "...",
    "cwe_id": "...",
    "references": ["..."]
  }
]
```

- `security.j2`: RAG context + code → security findings
- `bug_detection.j2`: Static findings as hints + code → bugs
- `style.j2`: Ruff issues as hints + code → style/readability
- `performance.j2`: Complexity hints + code → performance
- `fix.j2`: List of findings + code → {"changed": bool, "fixed_code": str}

---

### 11. AST Utilities & Analyzers

**AST Utilities** (`src/agents/ast_utils.py`)
- `parse(code)` → AST | None
- `attach_parents(tree)` → annotates each node with parent
- `loop_depth(node)` → how many enclosing loops
- `is_inside_loop(node)` → bool

**Bug Detection Analyzers** (Python only)
- `syntax.py`: `ast.parse()` catches SyntaxError
- `semantic.py`: Mutable defaults, `== None`, bare except, silently swallowed exceptions
- `runtime.py`: `open()` without `with`, `assert(tuple)` always true

**Performance Analyzers** (Python only)
- `complexity.py`: Nested loops (depth ≥2), long functions (>80 lines)
- `memory_leaks.py`: Unbounded containers in loops (heuristic). **Uses explicit if/elif, NOT ternary precedence** (bug #10)
- `hotspots.py`: String `+=` in loops, repeated `sorted()`/`list()` in loops

---

### 12. LangGraph Orchestrator

**State** (`src/agents/orchestrator/state.py`)
```python
class PRReviewState(TypedDict):
    pr_info: PRInfo
    files: dict[str, str]
    status: ReviewStatus
    findings: Annotated[list[Finding], add_findings]  # parallel reducer
    agent_results: Annotated[dict, add_agent_results]  # parallel reducer
    fix_results: list[Any]
    errors: list[str]
```

**Reducers** (`add_findings`, `add_agent_results`) merge parallel writes.

**Nodes** (`src/agents/orchestrator/nodes.py`)
- Each node: `async def node_name(state) -> dict` returns updates
- Parallel nodes: security, bug, style, performance
- Conditional: `should_apply_fixes(state)` → "apply_fixes" or "skip_fixes"

**Graph** (`src/agents/orchestrator/graph.py`)
```
initialize → fetch_pr → check_success
                    ↓
        ┌───────────┼───────────┐
        ↓           ↓           ↓ (parallel edges)
     security     bug      style/perf
        ↓           ↓           ↓
        └───────────┼───────────┘
           aggregate_findings
                 ↓
           [conditional]
           ↓           ↓
      apply_fixes  skip_fixes
           ↓           ↓
         test_pr ←─────┘
           ↓
        finalize
           ↓
          END
```

---

### 13. FastAPI Application (`src/main.py`)

**Lifespan**: Startup (configure logging), shutdown (cleanup).

**Middleware Stack** (right-to-left execution order):
1. HMACAuthMiddleware (for `/webhook/github`)
2. CorrelationIDMiddleware (sets X-Correlation-ID)
3. RateLimitMiddleware (sliding window 60/min)
4. CORSMiddleware (allow-origins from config)

**Routers**:
- `health.py`: GET `/health`, GET `/ready`
- `review.py`: POST `/reviews` (202), GET `/reviews` (paginated), GET `/reviews/{id}`
- `sse.py`: GET `/sse/reviews/{id}` (SSE stream)
- `webhook.py`: POST `/webhook/github` (HMAC validated)

**In-Memory Storage** (MVP)
- Reviews stored in `_reviews: dict[str, Review]`
- Production: use a real database (PostgreSQL, etc.)

---

### 14. SSE Streaming (`src/api/endpoints/sse.py`)

**get_or_create_channel(review_id)**: Create asyncio.Queue on first **publish**, not on listener connect (bug #5).

**publish_event(review_id, event_type, data)**:
- Gets or creates channel
- Puts event dict into queue
- Can be called from any node

**_event_stream(review_id)** (generator):
- Waits on `asyncio.wait()` for queue events or 30-second ping timeout
- Yields SSE-formatted: `data: {json}\n\n`
- Closes on TERMINAL_STATUSES (completed, failed)

---

### 15. Middleware Details

**CorrelationIDMiddleware**:
- Extract `X-Correlation-ID` header or generate UUID
- Call `set_correlation_id()` to update contextvars
- Response includes header

**RateLimitMiddleware**:
- Sliding window per client IP
- Trim old requests outside 60-second window
- Return 429 if exceeded

**HMACAuthMiddleware**:
- Skip `/health`, `/ready`, list routes
- For `/webhook/github`: verify `x-hub-signature-256` header
- HMAC-SHA256: `sha256=hex(hmac(secret, body))`
- Return 403 if invalid

---

### 16. ChromaDB Client (`src/infrastructure/chromadb/client.py`)

**Modes**:
- `embedded` (default): `PersistentClient(path)` — local file-based
- `http`: `HttpClient(host, port)` — external server

**Methods**:
- `get_collection()` → lazy init, return collection or None
- `query_knowledge(query, top_k)` → list[str] (returns documents or empty list)
- `upsert_documents(documents, metadatas)` → upsert with IDs

**Failure Handling**: Any exception logged, returns empty/None gracefully.

---

### 17. API Schemas (`src/api/schemas/review.py`)

- `CreateReviewRequest`: `pr_url` OR `(owner, repo, pr_number)`
- `ReviewResponse`: summary (id, status, pr_number, findings, fixes, timestamps)
- `ReviewDetailResponse`: full + findings grouped by category
- `ListReviewsResponse`: paginated items + total/page/page_size
- `HealthResponse`, `ReadyResponse`

---

### 18. Review Endpoint Workflow

**POST /api/v1/reviews** (202 Accepted)
1. Parse `pr_url` via regex or use `(owner, repo, pr_number)`
2. Create `Review` object, store in `_reviews[id]`
3. Launch `asyncio.create_task(_run_review(id))`
4. Return 202 + ReviewResponse immediately

**_run_review(review_id)** (background task)
1. Update status → ANALYZING
2. Fetch PR data via GitHubService (if not cached)
3. Invoke LangGraph with state
4. Unpack results (findings, agent_results, fix_results)
5. Group agent_results into Review.agent_results dict (bug #7)
6. Update status → COMPLETED or FAILED
7. Publish SSE events

---

### 19. Constants (`src/core/constants.py`)

| Constant | Value | Purpose |
|----------|-------|---------|
| `COMMIT_MESSAGE_PREFIX` | `[pr-review] GENAI=YES` | Required for enterprise pre-receive hooks |
| `FIXABLE_SEVERITIES` | `(critical, high, medium)` | Severity threshold for auto-fix |
| `FIX_CATEGORY_ORDER` | `(security, bug, style, performance)` | Commit order |
| `MAX_FIX_FILES_PER_CATEGORY` | 10 | Limit files touched per category |
| `SOURCE_EXTENSIONS` | tuple of `.py`, `.java`, `.kt`, etc. | Reviewable file types |
| `PYTHON_EXTENSIONS` | `(.py,)` | For AST analysis |
| `MAX_CODE_CHARS_FOR_RAG` | 2000 | Truncate code for RAG queries |

---

### 20. Worker (`src/worker.py`)

**ARQ WorkerSettings** (class attribute, NOT method — bug #1):
```python
class WorkerSettings:
    redis_settings = get_redis_settings()  # class attribute
    max_jobs = 5
    job_timeout = 600
```

Launch: `.venv/bin/arq src.worker.WorkerSettings`

---

## Testing Strategy

- **Unit**: services (mocked httpx/LLM), `_extract_json`, exceptions, models, fix-agent filtering, memory-leak analyzer
- **Integration**: full graph with mocked LLM/GitHub, verify state progression
- **No Credentials**: mocks + respx (httpx request spy) for API testing
