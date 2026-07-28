# Cap PR Review — AI Multi-Agent PR Analysis System

**Status**: Backend complete ✅ | Documentation complete ✅ | Dashboard (Phase 10) pending

An AI-powered system that automatically analyzes GitHub PRs using 5 specialized agents (security, bugs, style, performance, fixes), streams real-time progress via SSE, and commits auto-fixes directly to the PR head branch.

## Quick Start

### Prerequisites

- Python 3.12+ (any 3.12+ interpreter works; `make venv`/`make install` hardcode
  `python3.14` specifically — if you don't have that exact version, create the
  venv manually first with whatever 3.12+ you have, e.g. `python3.12 -m venv .venv`,
  then run `make install` to reuse it)
- Node 18+ (for dashboard) — verified with Node 24
- Docker + Docker Compose (for Redis)
- GitHub Enterprise or public GitHub account
- An LLM API key for at least one supported provider — DeepSeek is the
  configured default (`MODEL_PROVIDER=deepseek`, `PRIMARY_MODEL=deepseek-v4-pro`
  in `.env.example`); Anthropic/OpenAI/Gemini also work by changing
  `MODEL_PROVIDER`/`PRIMARY_MODEL` and the matching `*_API_KEY`

### Setup

```bash
# 1. Create venv and install dependencies
python3.12 -m venv .venv   # or python3.14, or `make venv` if you have 3.14
source .venv/bin/activate
pip install -e ".[dev]"
# Note: the `dev`/`observability` extras in pyproject.toml are currently
# missing their [project.optional-dependencies] table header, so `[dev]`
# doesn't install as a distinct extra — but every dev package (pytest,
# ruff, honcho, respx) is already duplicated in the base `dependencies`
# list, so nothing is actually missing from this command.

# 2. (Optional) Install RAG extras for ChromaDB + embeddings
pip install -e ".[rag]"

# 3. Copy env template and configure
cp .env.example .env
# Edit .env with your API keys and GitHub token

# 4. Start Redis
make up
# ChromaDB is NOT a separate container — it runs embedded (PersistentClient)
# by default (CHROMADB_MODE=embedded), so `make up` only starts Redis.

# 5. Run backend
make run
# API now at http://localhost:8000
curl http://localhost:8000/health   # should return {"status":"healthy"}

# 6. (Later) Run dashboard
cd dashboard
npm install
npm run dev
# Dashboard at http://localhost:5173 (Vite dev server proxies /api -> :8000)

# 7. Run the test suite
cd ..
pytest -q   # or: make test
# 112 tests should pass. Tests live in tests_local/, not tests/.
```

### Installation checklist

Use this to confirm a from-scratch setup is actually working, not just that
commands ran without error:

- [ ] `.venv` created with Python 3.12+; `python -c "import sys; print(sys.version)"` confirms it
- [ ] `pip install -e ".[dev]"` completed; `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/uvicorn`, `.venv/bin/honcho` all exist
- [ ] `.env` copied from `.env.example` and filled in: at minimum one LLM key (`LLM_API_KEY` for DeepSeek, or `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` if you switched provider) and `GITHUB_TOKEN`
- [ ] `make up` succeeded and `docker ps` shows a healthy `redis` container on port 6379
- [ ] `make run` succeeded; `curl http://localhost:8000/health` returns `{"status":"healthy"}` and `/ready` returns `{"status":"ready",...}`
- [ ] `cd dashboard && npm install && npm run dev` succeeded; http://localhost:5173 loads and its network tab shows `/api/v1/reviews` returning `200` (proxy to the backend working)
- [ ] `pytest -q` (from repo root) reports `112 passed`, not a collection error — if you see "No files were found in testpaths," check `pyproject.toml`'s `testpaths` still points at `tests_local`, not `tests`
- [ ] (Optional, only if exposing this publicly) `API_KEY` set in `.env` — gates `POST /reviews`, fix approve/reject/apply, and test-run endpoints behind an `X-API-Key` header; leave unset for local dev
- [ ] (Optional) `make ingest` run and `pip install -e ".[rag]"` done, if you want live ChromaDB/OWASP RAG instead of the hardcoded security-knowledge fallback

The `eval/`, `eval_PR/`, and `eval_harness/` subsystems are independent of the
above and have their own setup — see [eval/README.md](eval/README.md),
[eval_PR/README.md](eval_PR/README.md), and
[eval_harness/eval_harness/README.md](eval_harness/eval_harness/README.md).

## Project Structure

```
src/
├── core/                  # Config, logging, exceptions, constants
├── models/                # Pydantic domain models (Finding, Review, etc.)
├── api/
│   ├── endpoints/         # FastAPI routes (health, review, webhook, sse)
│   ├── middleware/        # Correlation, rate limit, HMAC auth
│   └── schemas/           # Request/response models
├── agents/
│   ├── base.py            # BaseAnalysisAgent ABC
│   ├── orchestrator/      # LangGraph state, nodes, graph
│   ├── security/          # SecurityAgent + RAG retriever
│   ├── bug_detection/     # BugDetectionAgent + AST analyzers
│   ├── style/             # StyleAgent + Ruff integration
│   ├── performance/       # PerformanceAgent + complexity/memory analyzers
│   └── fix/               # FixAgent (commits fixes via GitHub API)
├── services/
│   ├── llm_service.py     # ChatAnthropic wrapper + JSON extraction
│   ├── github_service.py  # GitHub REST API client
│   └── git_service.py     # Git operations (no local clone)
├── infrastructure/
│   ├── chromadb/          # ChromaDB client + knowledge queries
│   └── redis/             # ARQ queue interface
├── prompts/               # Jinja2 templates for agent prompts
├── main.py                # FastAPI app entry point
└── worker.py              # ARQ worker (background jobs)

knowledge_base/
├── owasp/
│   ├── top10_2021.json    # OWASP top 10 data
│   └── cwe_mappings.json  # CWE vulnerability definitions

scripts/
└── ingest_owasp.py        # Load OWASP knowledge into ChromaDB

docs/
├── HLD.md                 # High-level design (architecture, flow)
├── LLD.md                 # Low-level design (detailed specs)
└── USER_FLOWS.md          # User flows & integration guide

tests/                      # Unit + integration tests (pytest-asyncio)
```

## API Overview

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness check |
| `/ready` | GET | Readiness + version |
| `/api/v1/reviews` | POST | Create review (202 Accepted) |
| `/api/v1/reviews` | GET | List reviews (paginated) |
| `/api/v1/reviews/{id}` | GET | Get review details + findings |
| `/api/v1/sse/reviews/{id}` | GET | SSE stream (live progress) |
| `/api/v1/webhook/github` | POST | GitHub webhook (HMAC verified) |

## Example Usage

### Manual Review (API)

```bash
curl -X POST http://localhost:8000/api/v1/reviews \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'

# Response: 202 Accepted
{
  "id": "abc123",
  "status": "pending",
  "pr_number": 123,
  ...
}

# Poll for results
curl http://localhost:8000/api/v1/reviews/abc123
```

### GitHub Webhook

1. Go to repo Settings → Webhooks → Add webhook
2. Payload URL: `https://your-api.com/api/v1/webhook/github`
3. Secret: (set in .env as `GITHUB_WEBHOOK_SECRET`)
4. Events: Pull requests
5. When PR opened/updated → review auto-triggers

## Key Decisions & Trade-offs

### Parallel Agent Execution
✅ 4 analysis agents run concurrently (LangGraph fan-out/fan-in)  
⚡ Reduces review time by ~75% vs. serial execution

### No Local Git Clone
✅ All Git operations via GitHub REST API  
⚡ Avoid disk I/O; simpler deployment; works with GitHub Enterprise

### One Commit Per Category
✅ Fixes grouped by severity category (security → bug → style → performance)  
⚡ Atomic rollback; clear audit trail; smaller commits

### RAG with Graceful Fallback
✅ ChromaDB OWASP retrieval for security context  
✅ Hardcoded fallback if ChromaDB unavailable  
⚡ Optional dependency; system still works without RAG

### SSE for Real-time Updates
✅ React dashboard streams progress without polling  
⚡ Low-latency, connection-efficient

### In-Process MVP
✅ Reviews run as `asyncio.create_task()` in API process  
⚠️ **Production**: Enqueue to Redis/ARQ for durability & horizontal scaling

## Critical Implementation Details

> See `Build_from_Scratch.md` for the full spec and bug checklist.

1. ✅ **ARQ `redis_settings`** = class attribute (not @staticmethod)
2. ✅ **ChatAnthropic**: No `http_async_client` param; use env vars for SSL
3. ✅ **Git blobs**: Base64-encoded (not UTF-8)
4. ✅ **Commit messages**: Include `GENAI=YES` for enterprise hooks
5. ✅ **SSE**: `get_or_create_channel()` on first publish, not on connect
6. ✅ **structlog**: Never `event=`; use `sse_event=` instead
7. ✅ **Findings grouped**: Into `agent_results` dict by category
8. ✅ **FixAgent**: Medium severity included, max 10 files/category
9. ✅ **Memory leak analyzer**: Explicit if/elif (not ternary precedence)
10. ✅ **JSON extraction**: Robust fallback for LLM responses

## Configuration

All via `.env` (see `.env.example`):

```bash
# LLM
ANTHROPIC_API_KEY=<your-api-key>
PRIMARY_MODEL=claude-sonnet-4-6

# GitHub
GITHUB_TOKEN=<fine-grained-pat>
GITHUB_WEBHOOK_SECRET=<webhook-secret>

# API
CORS_ORIGINS='["http://localhost:5173"]'

# Storage
CHROMADB_MODE=embedded
REDIS_HOST=localhost
```

## Development

### Run Tests
```bash
make test  # pytest-asyncio
```

### Lint & Format
```bash
make lint   # ruff check
make fmt    # ruff format
```

### Ingest OWASP Knowledge
```bash
make ingest  # Load knowledge_base/ into ChromaDB
```

### Start All Services
```bash
make up     # Start Redis
make run    # Start API (foreground)
# In another terminal:
npm run dev # Start dashboard (from dashboard/)
```

### Run Evals
```bash
python -m eval.finding_eval.run_eval  # finding agents: precision/recall/F1
python -m eval.fix_eval.run_eval      # fix agent: LLM-as-judge across model candidates
python -m eval.e2e_eval.run_eval      # finding -> fix, chained end-to-end
```
See [eval/README.md](eval/README.md) for the concepts, matching logic, and
metrics behind each stage. Results are viewable in the dashboard's Eval
Matrix page once generated.

## Architecture Highlights

### LangGraph Orchestrator Topology
```
initialize → fetch_pr → check_success
                    ↓
        [security] [bug] [style] [performance]  (parallel)
                    ↓
            aggregate_findings
                    ↓
            (conditional)
            ↓          ↓
      apply_fixes   finalize → END
            ↓          ↑
            └──────────┘
```

### Analysis Flow
Each agent:
1. Filters files by `SOURCE_EXTENSIONS` (Python, Java, JS, TS, Go, Rust, XML, YAML, etc.)
2. Per-file try/except (one failure ≠ halt)
3. AST + LLM analysis (where applicable)
4. Returns list of `Finding` objects
5. Base agent stamps `agent_name` on findings

### Fix Flow
1. Filter findings: only critical + high + medium severity
2. Group by category (security, bug, style, performance)
3. Limit to 10 files per category
4. LLM generates fixes (per-file)
5. Validate Python syntax with `compile()`
6. Commit to PR head branch via GitHub API
7. Update in-memory file dict (next category fixes prev. fixes)

## Performance

- **Typical review**: 30–60 seconds (PR size + LLM latency dependent)
- **Parallelism**: 4 agents save ~75% time vs. serial
- **Concurrency**: FastAPI + asyncio handles 100s of concurrent reviews
- **ChromaDB**: Embedded ~10ms/query; HTTP adds network cost

## Security

- ✅ **HMAC verification** on GitHub webhooks
- ✅ **Rate limiting** (60 req/min per IP)
- ✅ **Correlation IDs** for request tracing
- ✅ **No hardcoded secrets** (all from `.env`)
- ✅ **Optional SSL CA bundle** for enterprise gateways
- ⚠️ **MVP storage**: In-memory dict; production needs database

## Documentation

- **[HLD.md](docs/HLD.md)**: Architecture, components, dataflow
- **[LLD.md](docs/LLD.md)**: Implementation details, API contracts, AST analyzers
- **[USER_FLOWS.md](docs/USER_FLOWS.md)**: Integration guide, API examples, troubleshooting
- **[Build_from_Scratch.md](Build_from_Scratch.md)**: Complete specification (source of truth)

## Next Steps

1. ✅ **Backend complete**: API, agents, orchestrator tested
2. 📋 **Dashboard (Phase 10)**: React 18 + Vite + TailwindCSS + SSE streaming
3. 🧪 **Full integration test**: Real GitHub PR with real LLM
4. 🚀 **Production deployment**: Database (not in-memory), Redis/ARQ queuing, load balancing

## Troubleshooting

**Review stuck in ANALYZING?**
- Check API logs for agent errors
- Verify `ANTHROPIC_API_KEY` is valid
- Check `GITHUB_TOKEN` permissions

**ChromaDB not initialized?**
- Ensure `CHROMADB_MODE=embedded` and `.chroma` is writable
- Or set `CHROMADB_MODE=http` and run external server

**SSE stream not updating?**
- Reload browser, check browser console
- Verify review ID matches
- Check logs for `sse_published` events

**`pytest` reports "No files were found in testpaths" or errors importing `eval_harness`'s vendored dataset scripts?**
- `pyproject.toml`'s `testpaths` must be `tests_local`, not `tests` — the latter doesn't exist and pytest silently falls back to scanning the whole repo, which sweeps in unrelated third-party files under `eval_harness/`

**Dashboard's "Run Tests" button always says "no directory found — nothing to run"?**
- That feature (`src/services/test_runner.py`) clones the PR's head branch and looks for a `tests_local/` directory in it — if the PR you're reviewing doesn't have tests there, this is correct behavior, not a bug

**Getting `"Could not resolve authentication method"` when running something (e.g. `eval_harness`) from a directory other than the repo root?**
- `Settings` loads `.env` from an absolute path anchored to the repo root, so this should no longer happen as of the fix in this session — if you still see it, confirm you're on a build that includes the `src/core/config.py` `_REPO_ROOT_ENV_FILE` fix

**`make up` fails or nothing is listening on 6379?**
- Confirm `docker-compose.yml` has a `redis` service defined (it does as of this session's fix) and `docker ps` shows `cap-pr-review-redis` healthy

See [USER_FLOWS.md](docs/USER_FLOWS.md) for more details.

## License

MIT

## Authors

- Built from spec: [Cap PR Review Specification](Build_from_Scratch.md)
- Implementation: Claude Code (Anthropic)
