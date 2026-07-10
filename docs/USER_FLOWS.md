# User Flows & Integration Guide

## Flow 1: Manual PR Review (API)

**Actor**: Developer or CI system

### Steps

1. **Trigger Review**
   ```bash
   curl -X POST http://localhost:8000/api/v1/reviews \
     -H "Content-Type: application/json" \
     -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
   ```
   
   Or:
   ```json
   {
     "owner": "owner",
     "repo": "repo",
     "pr_number": 123
   }
   ```

2. **Server Response** (202 Accepted)
   ```json
   {
     "id": "abc123def456",
     "status": "pending",
     "pr_number": 123,
     "pr_title": "Add user authentication",
     "total_findings": 0,
     "total_fixes": 0,
     "created_at": "2026-06-26T17:00:00Z",
     "updated_at": "2026-06-26T17:00:00Z",
     "completed_at": null
   }
   ```

3. **Poll for Results** (GET `/api/v1/reviews/{id}`)
   ```bash
   curl http://localhost:8000/api/v1/reviews/abc123def456
   ```
   Response (once complete):
   ```json
   {
     "id": "abc123def456",
     "status": "completed",
     "pr_number": 123,
     "pr_title": "Add user authentication",
     "pr_author": "alice",
     "findings_by_category": {
       "security": [
         {
           "id": "find-1",
           "severity": "high",
           "title": "SQL Injection in auth.py",
           "description": "User input concatenated into query",
           "location": {"file_path": "auth.py", "start_line": 42},
           "suggestion": "Use parameterized queries",
           "cwe_id": "CWE-89"
         }
       ],
       "bug_detection": [...],
       "style": [...],
       "performance": [...]
     },
     "total_findings": 8,
     "total_fixes": 3,
     "completed_at": "2026-06-26T17:02:30Z"
   }
   ```

4. **Monitor Progress (SSE)**
   ```bash
   curl http://localhost:8000/api/v1/sse/reviews/abc123def456
   ```
   
   Output (live stream):
   ```
   data: {"type": "status_update", "status": "fetching"}
   
   data: {"type": "status_update", "status": "analyzing"}
   
   data: {"type": "finding", "agent": "security", "finding": {...}}
   
   data: {"type": "status_update", "status": "completed"}
   
   ```

---

## Flow 2: Webhook (GitHub Integration)

**Actor**: GitHub (automatic on PR events)

### Setup

1. **Create Webhook**
   - GitHub Repo → Settings → Webhooks → Add webhook
   - Payload URL: `https://your-api.com/api/v1/webhook/github`
   - Content type: `application/json`
   - Events: `pull requests`
   - Secret: `<generate and paste into .env as GITHUB_WEBHOOK_SECRET>`

2. **Environment**
   ```bash
   GITHUB_WEBHOOK_SECRET=<your-secret>
   GITHUB_TOKEN=<fine-grained-pat>
   ```

### Trigger

**When PR opened/reopened/synchronized:**

1. GitHub sends POST with HMAC signature
2. API validates signature via `HMACAuthMiddleware`
3. Creates Review, launches background task
4. Returns 202 with review ID
5. Pipeline runs asynchronously
6. If fixes found → commits to PR head branch

### Result

**On PR branch** (after ~1-2 min):
```
✓ [pr-review] GENAI=YES: fix security issues (2 files)
✓ [pr-review] GENAI=YES: fix bug_detection issues (1 file)
✓ [pr-review] GENAI=YES: fix style issues (3 files)
```

**On PR page**: Reviewers see new commits with analysis results.

---

## Flow 3: Dashboard (React SPA)

**Actor**: Developer reviewing PRs

### Steps

1. **Open Dashboard**
   ```
   http://localhost:5173/
   ```

2. **Dashboard Page** (list of reviews)
   - Shows recent reviews with status badges
   - Click on a review to see details

3. **Review Detail Page**
   - **Input**: PR URL or manual trigger button
   - **Live Feed**: Table of findings grouped by category
   - **Progress**: Status updates streamed via SSE
     - "fetching" → "analyzing" → "fixing" → "completed"
   - **Findings Table**: Severity, title, file, line, suggestion
   - **Action**: View on GitHub, export findings (future)

4. **Real-time Updates**
   - As agents complete, findings appear in the table
   - Status bar updates (1/5 agents done → 2/5, etc.)
   - SSE stream closed when status = completed or failed

---

## Flow 4: Full Example Walk-through

### Scenario

Repository with a PR adding user login:
- `auth.py` (30 lines, uses `format()` in SQL query) ← **bug**
- `api.py` (200 lines) ← **high complexity**
- `tests/test_auth.py` (50 lines) ← **good**

### Timeline

**T=0s**: User opens dashboard, clicks "Analyze PR"

**T=1s**: 
- Status: FETCHING
- API calls GitHub, downloads PR metadata + file contents

**T=2s**: 
- Status: ANALYZING
- LangGraph initialized; 4 agents fan out

  - SecurityAgent queries ChromaDB, finds SQL injection hint in code
  - BugDetectionAgent runs AST, finds `None` comparison with `==`
  - StyleAgent runs Ruff, finds missing docstring
  - PerformanceAgent runs AST, finds single-loop (not nested)

**T=5s**:
- Status: FIXING
- Aggregate findings: 4 total

  ```
  - security: "SQL Injection in auth.py" (high severity) ← fixable
  - bug: "Bad None comparison in auth.py" (low severity) ← not fixable (low)
  - style: "Missing docstring in api.py" (low severity) ← not fixable
  - performance: (none)
  ```
  
- FixAgent:
  - Filter: only critical + high + medium (so just security finding)
  - Generate fix for auth.py (parameterized query)
  - Validate syntax: ✓ OK
  - Commit to PR head branch
  - Status: TESTING

**T=8s**:
- Status: COMPLETED
- Dashboard shows:
  - total_findings: 4
  - total_fixes: 1
  - Findings table populated
  - New commit visible on PR (if GitHub polling enabled)

---

## Flow 5: Error Scenarios

### Scenario: LLM API Unavailable

1. **Symptom**: Agent fails mid-run
2. **Handling**: Per-file try/except catches error
3. **Result**: Other files still analyzed; failed file marked in logs
4. **Review Status**: COMPLETED (partial results)

### Scenario: GitHub Rate Limit

1. **Symptom**: `GitHubRateLimitError` during file fetch
2. **Retry Policy**: Linear backoff, 5 attempts
3. **If Still Failed**: Review marked FAILED; error message returned
4. **Dashboard**: Shows error in ReviewDetailResponse

### Scenario: Fix Commit Fails

1. **Symptom**: `GitService.commit_fixes()` returns 403 (branch protection)
2. **Handling**: FixAgent logs error, marks fixes as failed
3. **Result**: Findings still reported; no commit made
4. **Review Status**: COMPLETED (findings only, no fixes)

---

## Configuration Reference

### Environment Variables

```bash
# App
APP_ENV=development
LOG_LEVEL=INFO
LOG_JSON=false

# API
API_PORT=8000
CORS_ORIGINS='["http://localhost:5173"]'

# LLM (Anthropic)
PRIMARY_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=<your-api-key>

# GitHub
GITHUB_TOKEN=<fine-grained-pat>
GITHUB_API_BASE_URL=https://api.github.com
GITHUB_WEBHOOK_SECRET=<webhook-secret>

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# ChromaDB
CHROMADB_MODE=embedded
CHROMADB_PERSIST_DIR=.chroma
```

### Startup Checklist

- [ ] Python 3.12+ installed
- [ ] `.venv` created and activated
- [ ] Dependencies installed: `pip install -e ".[dev]"`
- [ ] `.env` configured (see `.env.example`)
- [ ] Redis running: `docker compose up -d redis`
- [ ] Backend started: `make run`
- [ ] Frontend started: `npm run dev` (in `dashboard/`)
- [ ] Dashboard accessible at `http://localhost:5173`

---

## API Reference Summary

| Endpoint | Method | Auth | Response | Purpose |
|----------|--------|------|----------|---------|
| `/health` | GET | No | `{status: "healthy"}` | Liveness check |
| `/ready` | GET | No | `{status, env, version}` | Readiness check |
| `/api/v1/reviews` | POST | No | 202 + ReviewResponse | Create review |
| `/api/v1/reviews` | GET | No | ListReviewsResponse | List reviews |
| `/api/v1/reviews/{id}` | GET | No | ReviewDetailResponse | Get review details |
| `/api/v1/sse/reviews/{id}` | GET | No | Server-Sent Events | Stream progress |
| `/api/v1/webhook/github` | POST | HMAC | `{status, review_id}` | GitHub webhook |

---

## Troubleshooting

### "Review stuck in ANALYZING"
- Check API logs for agent errors
- Verify LLM API key is valid
- Check GitHub token permissions

### "No findings after review completes"
- Verify PR has actual code issues (test on a known-bad PR)
- Check agent logs for `agent_file_failed` or `llm_json_parse_failed`

### "Chrome DB not initialized"
- Ensure `CHROMADB_MODE=embedded` and `.chroma` dir is writable
- Or set `CHROMADB_MODE=http` and run external server

### "SSE stream not updating"
- Clear browser cache, reload
- Check client ID matches review ID
- Verify API is publishing events (grep logs for `sse_published`)

---

## Performance Tips

1. **Parallel Agents**: 4 analysis agents run concurrently; total time ~30–60s for typical PR
2. **RAG Queries**: ChromaDB embedded mode is fast (~10ms); HTTP adds network latency
3. **File Limits**: FixAgent limits to 10 files/category; large PRs may not fix all issues
4. **LLM Cost**: Each agent makes 1 LLM call per file; large PRs = higher cost

---

## Security Notes

- **Never commit `.env`** (contains secrets)
- **Webhook Secret**: Must match GitHub secret; HMAC validated on every webhook
- **GitHub Token**: Store securely; use fine-grained PATs with minimal scopes
- **LLM API Key**: Never log or expose; always from env vars
- **CORS**: Whitelist only your dashboard origin
