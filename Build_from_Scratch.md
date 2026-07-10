# BUILD FROM SCRATCH - Cap PR Review

## Instructions for Claude
Recreate this project from scratch. Build incrementally in phases, verifying each phase works before proceeding.
Use Python 3.12, async/await, Pydantic v2 throughout. Derive folder structure from module descriptions below.

---

## 1. Overview
AI-powered multi-agent system that reviews PRs on GitHub Enterprise. A LangGraph orchestrator coordinates 5 agents to analyze code, auto-fix critical/high/medium issues (one commit per category pushed directly to PR's head branch via GitHub REST API), and report findings via a real-time SSE dashboard.

**Workflow:** Webhook/manual trigger -> Fetch PR -> 4 agents analyze in parallel (fan-out) -> Barrier sync -> Fix Agent commits per category -> TestPRAgent returns PR URL (test gen disabled) -> Dashboard shows progress via SSE

---

## 2. Tech Stack

- **Backend:** Python 3.12, FastAPI, uvicorn
- **Orchestration:** LangGraph (StateGraph, fan-out/fan-in)
- **LLMs:** `langchain_anthropic.ChatAnthropic` -> Visa GenAI Gateway (`https://genai-api.visa.com`)
- **Vector DB:** ChromaDB + sentence-transformers (all-MiniLM-L6-v2)
- **Queue:** Redis + ARQ (MVP runs as background task in API process)
- **Database:** In-memory dict (MVP)
- **Frontend:** React 18 + TypeScript + Vite + TailwindCSS
- **GitHub:** GitHub Enterprise (`github.trusted.visa.com`) via Fine-Grained PAT

---

## 3. Architecture

**Layers:** Presentation (React SPA + GitHub webhooks) -> API (FastAPI + middleware: CORS, rate limit, correlation ID, HMAC auth) -> Processing (LangGraph pipeline as asyncio background task) -> Data (Redis, in-memory dict, ChromaDB)

**LangGraph topology:**
`initialize -> fetch_pr -> check_success -> [security, bug, style, performance] (parallel) -> aggregate_findings -> should_apply_fixes -> apply_fixes -> finalize -> END`

**Agents (all extend BaseAnalysisAgent ABC with `run()` and `analyze()` methods):**
- **SecurityAgent:** RAG retrieval from ChromaDB (OWASP/CWE, top-5, fallback to hardcoded) + LLM analysis -> Findings with CWE IDs
- **BugDetectionAgent:** AST analyzers (syntax, semantic, runtime - .py only) + LLM -> Bug findings
- **StyleAgent:** Ruff subprocess (if available) + LLM (skip Ruff duplicates) -> Style findings
- **PerformanceAgent:** AST analyzers (complexity, memory leaks, hotspots - .py only) + LLM -> Perf findings
- **FixAgent:** Filters critical/high/medium findings, groups by category, generates fixes via LLM (max 10 files/category), validates syntax with `compile()`, commits per category via GitHub Git Data API
- **TestPRAgent:** Currently disabled - just returns PR URL

**Git commit flow (NO local clone - all via GitHub REST API):**
1. GET ref -> HEAD SHA
2. GET commit -> tree SHA
3. POST blobs (base64 encoded content)
4. POST trees
5. POST commits (message includes `GENAI=YES`)
6. PATCH refs -> update branch

---

## 3.1 Folder Structure
```text
src/
├── core/                  # Config (Pydantic Settings), logging (structlog), exceptions, constants
├── models/                # Pydantic v2 domain models (Finding, FixResult, Review, etc.)
├── api/
│   ├── endpoints/         # health.py, webhook.py, review.py, sse.py
│   ├── middleware/        # auth (HMAC), rate_limit, correlation IDs
│   └── schemas/           # Request/response Pydantic models
├── agents/
│   ├── base.py            # BaseAnalysisAgent ABC
│   ├── orchestrator/      # LangGraph state, graph, nodes, edges
│   ├── security/          # SecurityAgent + RAG (ChromaDB retriever, OWASP data)
│   ├── bug_detection/     # BugDetectionAgent + AST analyzers (syntax, semantic, runtime)
│   ├── style/             # StyleAgent + Ruff integration
│   ├── performance/       # PerformanceAgent + complexity/memory/hotspot analyzers
│   ├── fix/               # FixAgent – commits fixes directly to PR head branch via GitHub API
│   └── test_pr/           # TestPRAgent (test generation disabled for now, returns PR URL)
├── services/
│   ├── github_service.py  # GitHub Enterprise API client (fetch PRs, files, create PRs)
│   ├── llm_service.py     # Unified LLM service via ChatAnthropic + enterprise gateway
│   └── git_service.py     # Git operations via GitHub REST API (no local clone)
├── infrastructure/
│   ├── chromadb/          # ChromaDB client
│   ├── redis/             # ARQ queue
│   └── observability/     # LangFuse integration
├── prompts/templates/      # Jinja2 prompt templates
├── knowledge_base/owasp/   # top10_2021.json, cwe_mappings.json
├── main.py                # FastAPI app entry point
└── worker.py              # ARQ worker process
dashboard/                 # React frontend (Vite + TailwindCSS)
├── src/pages/             # Dashboard, ReviewDetail, TriggerReview
├── src/components/        # FindingsTable, AgentStatus, ReviewTimeline
├── src/hooks/             # useSSE (Server-Sent Events)
└── src/api/               # Axios API client
tests/                     # Unit + integration (pytest-asyncio)
scripts/                   # ingest_owasp.py
docs/                      # Issue tracking and setup documentation
infra/                     # Docker, AWS configs (future)
```

## 4. Key Design Decisions
1. Fan-out/fan-in via LangGraph with TypedDict state + Annotated reducers for parallel writes
2. Single model via enterprise gateway using `ChatAnthropic` with custom `base_url`
3. One commit per fix category (security -> bug -> style -> performance) via GitHub API
4. RAG for security: ChromaDB with sentence-transformer embeddings, graceful fallback
5. SSE for real-time updates with asyncio.Queue buffering (channel created on first publish, not on listener connect)
6. Temperature=0 for all LLM calls, `_extract_json()` handles markdown fences in responses
7. All HTTP clients use `cacerts.pem` for enterprise SSL

---

## 5. Module Specifications

### Core (`src/core/`)
- **config.py:** Pydantic Settings with groups: app, api, github, anthropic, redis, chromadb, langfuse, worker. Cached via `@lru_cache`. Loads from `.env`.
- **logging.py:** structlog with timestamper, level, JSON/console renderer, correlation ID via contextvars
- **exceptions.py:** Hierarchy: PRReviewError (base) -> GitHubAPIError (exp backoff, 3), GitHubRateLimitError (linear, 5), LLMError (exp, 3), LLMRateLimitError (linear, 5), LLMContextLengthError (none), AgentError (exp, 2), AgentTimeoutError (immediate, 1), RAGError (exp, 2), GitOperationError (immediate, 2), WebhookValidationError (none), QueueError (exp, 3)
- **constants.py:** `COMMIT_MESSAGE_PREFIX = "[pr-review] GENAI=YES"`, agent IDs, severity order, fix category order (security->bug->style->perf), `MAX_FIX_FILES_PER_CATEGORY = 10`, `SOURCE_EXTENSIONS = (".py", ".java", ".kt", ".js", ".ts", ".go", ".rs", ".xml", ".yml", ".yaml", ".properties")`

### Models (`src/models/`)
- **finding.py:** Enums (Category, Severity, Confidence), Location (file_path, start_line, end_line, snippet), Finding (id, category, severity, confidence, title, description, location, suggestion, references, cwe_id, agent_name, created_at), FixResult (id, finding_id, category, file_path, original_code, fixed_code, commit_sha, commit_message, success)
- **review.py:** ReviewStatus enum (pending->fetching->analyzing->fixing->testing->creating_pr->completed|failed), PRInfo (owner, repo, pr_number, title, author, head_branch, base_branch, head_sha), AgentResult (agent_name, status, findings, duration_seconds, error), Review (id, pr_info, status, agent_results, total_findings, total_fixes, fix_branch, fix_pr_url, triggered_by, error_message, timestamps)

### Services (`src/services/`)
- **llm_service.py:** Sets `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` env vars pointing to `cacerts.pem` at module load. Uses ChatAnthropic with: model, temperature=0, base_url, api_key, max_tokens, timeout=120.0, rate_limiter=InMemoryRateLimiter(requests_per_second=200). Has `_extract_json()` that tries: code fences -> full text -> find first `[` or `{` with matching close -> fallback `[]`.
- **github_service.py:** httpx.AsyncClient with `verify="cacerts.pem"`, Bearer token auth, base_url from settings. Methods: get_pr, get_pr_diff (Accept: diff header), get_pr_files, get_file_content, fetch_pr_data (combines all).
- **git_service.py:** httpx.AsyncClient, verify="cacerts.pem". `commit_fixes(owner, repo, branch, fixes, message)`: GET ref -> GET commit/tree -> POST blobs (base64!) -> POST tree -> POST commit -> PATCH ref. Returns new SHA.

### API (`src/api/`)
- **endpoints/health.py:** GET /health -> `{"status": "healthy"}`, GET /ready -> `{"status", environment, version}`
- **endpoints/webhook.py:** POST /webhook/github - HMAC-SHA256 verification, validates pull_request event, enqueues review
- **endpoints/review.py:** POST /reviews (accepts `{"pr_url"}` or `{"owner", "repo", "pr_number"}`), parses URL with regex `r"https://([^/]+)/([^/]+)/([^/]+)/pull/(\d+)"`, creates Review, launches `asyncio.create_task(_run_review)`, returns 202. GET /reviews (paginated list). GET /reviews/{id} (full review + findings).
  **After pipeline completes, populate 'agent_results' with Finding objects grouped by category.**
- **endpoints/sse.py:** GET /sse/reviews/{id} - yields from asyncio.Queue channel, ping every 30s, terminal events close stream. `publish_event()` uses `get_or_create_channel()` (creates queue on first publish, not on connect).
- **middleware/** auth (HMAC), rate_limit (sliding window, 60 req/min), correlation (X-Correlation-ID)
- **schemas/review.py:** Request/response Pydantic models

### Infrastructure (`src/infrastructure/`)
- **chromadb/client.py:** HTTP client to ChromaDB, fallback to EphemeralClient
- **redis/queue.py:** ARQ Redis pool, enqueue functions

### Worker (`src/worker.py`)
- ARQ WorkerSettings with `redis_settings` as CLASS ATTRIBUTE (not method!)

### Agents (`src/agents/`)
- **base.py:** ABC with `name`, abstract `analyze(code, file_path, context) -> list[Finding]`, concrete `run(files, context) -> list[Finding]` (iterates files, filters by SOURCE_EXTENSIONS, sets agent_name, per-file try/except)
- **orchestrator/state.py:** PRReviewState TypedDict with Annotated reducers (add_findings, add_fixes)
- **orchestrator/nodes.py:** Node functions with SSE event publishing at each stage
- **orchestrator/graph.py:** StateGraph construction with fan-out edges, conditional edges
- **security/agent.py + retriever.py:** ChromaDB query (top-5, code[:2000]), fallback hardcoded knowledge
- **bug_detection/agent.py + analyzers/** AST analyzers (.py guard), syntax/semantic/runtime
- **style/agent.py:** Ruff subprocess + LLM (skip duplicates)
- **performance/agent.py + analyzers/** complexity, memory_leaks (see bug fix #10), hotspots
- **fix/agent.py:** Filter critical/high/medium, group by category, max 10 files, per-file try/except, compile() validation, commit via GitService, update in-memory files dict for subsequent categories
- **test_pr/agent.py:** Returns PR URL only (test generation disabled)

### Dashboard (`dashboard/`)
- Vite + React 18 + TypeScript + TailwindCSS
- **vite.config.ts:** proxy `/api` -> `http://localhost:8000`
- **Pages:** Dashboard (reviews list), ReviewDetail (findings table + SSE progress), TriggerReview (single URL input -> POST /api/v1/reviews with {pr_url} -> redirect to /reviews/{id})
- **Components:** FindingsTable (severity badges), AgentStatus, ReviewTimeline
- **Hooks:** useSSE (EventSource hook)
- **CRITICAL:** ReviewDetail must update status from ANY event carrying `data.status`, not just `status_update` events

### Scripts + Knowledge Base
- **scripts/ingest_owasp.py:** Seeds ChromaDB with OWASP top10 + CWE data using sentence-transformers
- **knowledge_base/owasp/top10_2021.json:** Array of {id, name, description, cwes[], prevention[]}
- **knowledge_base/owasp/cwe_mappings.json:** Array of {id, name, description, category, severity, detection_patterns[]}

---

## 6. Critical Bugs to Avoid (implement correctly from start)

1. **ARQ `redis_settings`:** Must be a class attribute, NOT a `@staticmethod` method
2. **ChatAnthropic SSL:** DO NOT pass `http_async_client` - not supported. Use env vars (`SSL_CERT_FILE`)
3. **Git blobs:** MUST be base64 encoded (`{"content": b64_str, "encoding": "base64"}`). UTF-8 rejected by enterprise binary blocker hooks
4. **Commit messages:** MUST contain `GENAI=YES` (enterprise pre-receive hook)
5. **SSE race condition:** `publish_event()` must `get_or_create_channel()` (create queue on first publish, not on listener connect)
6. **structlog `event=`:** NEVER use `event=` as kwarg (reserved). Use `sse_event=` instead
7. **Review findings display:** After pipeline completes, group findings by category into `review.agent_results` dict with AgentResult objects
8. **Fix agent severity:** Include medium (`'critical', 'high', 'medium'`). Not just critical/high
9. **Fix agent limits:** Max 10 files per category, per-file try/except (one failure doesn't halt category)
10. **Memory leak analyzer:** Python ternary precedence bug - use explicit if/elif instead of `X and Y and Z if COND else W`
11. **File extensions:** SOURCE_EXTENSIONS must include .py, .java, .kt, .js, .ts, .go, .rs, .xml, .yml, .yaml, .properties
12. **CORS_ORIGINS in .env:** Wrap in single quotes: `CORS_ORIGINS='["http://localhost:5173"]'`
13. **Makefile:** Use `.venv/bin/python` not bare `python` (macOS has only `python3`)
14. **pyproject.toml:** Must have `[tool.hatch.build.targets.wheel] packages = ["src"]`
15. **LLM JSON parsing:** LLM returns JSON in markdown fences. `_extract_json()` must handle this robustly

---

## 7. Environment Variables

```bash
PRIMARY_MODEL=claude-opus-4-6:1m
FALLBACK_MODEL=claude-opus-4-6:1m
BASE_URL=[https://genai-api.visa.com](https://genai-api.visa.com)
MODEL_PROVIDER=anthropic
API_KEY=<jwt-token>
GITHUB_TOKEN=github_pat_<fine-grained-pat>
GITHUB_API_BASE_URL=[https://github.trusted.visa.com/api/v3](https://github.trusted.visa.com/api/v3)
GITHUB_WEBHOOK_SECRET=<secret>
REDIS_HOST=localhost
REDIS_PORT=6379
CHROMADB_HOST=localhost
CHROMADB_PORT=8000
CORS_ORIGINS='["http://localhost:5173"]'
```