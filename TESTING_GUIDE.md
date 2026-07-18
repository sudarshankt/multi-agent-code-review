# Testing Guide — Full Stack Setup & Integration

This guide walks you through setting up and testing the complete Cap PR Review system (backend + dashboard).

## Prerequisites

- ✅ Python 3.14.2 (verified)
- ✅ Node.js 24.18.0 (verified)
- ✅ Docker & Docker Compose (for Redis)
- ✅ GitHub account (create a fine-grained PAT)
- ✅ Anthropic API key

## Step 1: Backend Setup

### 1.1 Create Virtual Environment

```bash
cd /path/to/iiscCapStone-pr-review
python3.14 -m venv .venv
source .venv/bin/activate
```

### 1.2 Install Dependencies

```bash
pip install -e ".[dev]"
```

### 1.3 Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
# Required: LLM API (Deepseek or Anthropic-compatible)
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.deepseek.com/anthropic   # remove for native Anthropic
PRIMARY_MODEL=deepseek-v4-pro

# Required: GitHub
GITHUB_TOKEN=github_pat_xxxxx  # fine-grained PAT
GITHUB_WEBHOOK_SECRET=your-webhook-secret  # any random string

# Optional: For enterprise
# GITHUB_API_BASE_URL=https://github.enterprise.com/api/v3
```

### 1.4 Start Redis

```bash
docker compose up -d redis
# Verify: docker ps | grep redis
```

### 1.5 Start Backend

```bash
make run
# Or: .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 1.6 Test Backend Health

```bash
curl http://localhost:8000/health
# {"status":"healthy"}

curl http://localhost:8000/ready
# {"status":"ready","environment":"development","version":"0.1.0"}
```

✅ **Backend is ready!**

---

## Step 2: Dashboard Setup

### 2.1 Install Dependencies

```bash
cd dashboard
npm install
```

### 2.2 Start Dev Server

```bash
npm run dev
```

Expected output:
```
  Local:   http://localhost:5173/
```

Open http://localhost:5173 in your browser.

✅ **Dashboard is running!**

---

## Step 3: Test Full Integration

### 3.1 Manual PR Review (via Dashboard)

**Steps:**

1. Open http://localhost:5173 in your browser
2. Enter a GitHub PR URL:
   ```
   https://github.com/owner/repo/pull/123
   ```
   (Use a **real PR** from a public repo, e.g., facebook/react)

3. Click **"Analyze PR"**

4. Watch the **live progress**:
   - Status changes: pending → fetching → analyzing → fixing → completed
   - Findings appear in real-time
   - Findings grouped by category (security, bugs, style, performance)

### 3.2 Check Backend Logs

In the backend terminal, you should see:
```
[info     ] review_created                review_id=abc123... owner=facebook repo=react pr_number=...
[info     ] fetched_pr_data              owner=facebook repo=react pr_number=... changed=12 source_files=8
[info     ] agent_run_complete           agent=security files=8 findings=2 duration_seconds=8.234
[info     ] agent_run_complete           agent=bug_detection files=8 findings=1 duration_seconds=5.123
[info     ] agent_run_complete           agent=style files=8 findings=3 duration_seconds=4.567
[info     ] agent_run_complete           agent=performance files=8 findings=0 duration_seconds=3.890
[info     ] review_complete              review_id=abc123... findings=6
```

### 3.3 Verify Findings Display

The dashboard should show a table with:
- **Severity badges** (critical, high, medium, low, info)
- **File + line number** (e.g., `auth.py:42`)
- **Title & description**
- **Suggestion** for how to fix
- **CWE link** (clickable for security findings)

Example findings:
```
Security (2 issues)
  [HIGH] SQL Injection in auth.py:42
    Use parameterized queries instead of string concatenation
    → CWE-89

Bug Detection (1 issue)
  [LOW] Bad None comparison in api.py:128
    Use 'is None' instead of '== None'

Style (3 issues)
  [LOW] Missing docstring in handler.py:15
  ...

Performance (0 issues)
```

✅ **Integration works!**

---

## Step 4: Test with Webhook (Optional)

### 4.1 Set Up GitHub Webhook

**Prerequisites:**
- A GitHub repo you own (or have admin access to)
- Public internet-accessible API endpoint (e.g., ngrok tunnel)

**Steps:**

1. Start an ngrok tunnel:
   ```bash
   ngrok http 8000
   # Forwarding: https://abc123.ngrok.io -> http://localhost:8000
   ```

2. Go to repo Settings → Webhooks → Add webhook

   - Payload URL: `https://abc123.ngrok.io/api/v1/webhook/github`
   - Content type: `application/json`
   - Events: `Pull requests`
   - Secret: (use value from `.env` `GITHUB_WEBHOOK_SECRET`)
   - Active: ✓

3. Create or update a PR on the repo

4. GitHub sends webhook → Review auto-triggers on the backend

5. Watch dashboard at http://localhost:5173 → click on the review

---

## Step 5: Test Auto-Fixes (Optional)

If you want to see the **FixAgent** commit fixes to the PR:

### 5.1 Create a Test PR with Known Issues

```python
# test.py
import hashlib

def process_user(user_id):
    query = "SELECT * FROM users WHERE id = " + str(user_id)  # SQL injection
    db.execute(query)
    
    password = None
    if password == None:  # Bad None comparison
        raise ValueError("No password")
```

### 5.2 Push & Create PR

```bash
git add test.py
git commit -m "Add test file"
git push origin test-branch
# Create PR via GitHub UI
```

### 5.3 Review Will Auto-Fix

If the FixAgent has permission (GitHub token has `contents:write`), it will:
1. Generate fixes for the issues
2. Commit them to the PR head branch
3. You'll see commits like:
   ```
   [pr-review] GENAI=YES: fix security issues (1 file)
   [pr-review] GENAI=YES: fix style issues (1 file)
   ```

---

## Troubleshooting

### "Review stuck in ANALYZING"

**Check logs:**
```bash
# Backend terminal
# Look for errors in the logs
```

**Common causes:**
- LLM API key invalid → check `.env` `LLM_API_KEY` and `LLM_BASE_URL`
- GitHub token invalid → check `.env` `GITHUB_TOKEN`
- Network issue → check internet connection

### "404 Not Found" when accessing dashboard

**Fix:**
```bash
# Make sure backend is running
curl http://localhost:8000/health
# Should return {"status":"healthy"}

# Make sure dashboard is running
npm run dev  # in dashboard/
```

### "PR URL invalid"

**Expected format:**
```
https://github.com/owner/repo/pull/123
```

Not:
- `https://github.com/owner/repo/issues/123` (issues, not PRs)
- `github.com/owner/repo/pull/123` (missing https://)
- `https://github.com/owner/repo/pull/123/files` (extra path)

### "EventSource failed"

**Cause:** SSE connection lost

**Fix:**
- Reload browser (Cmd+R / Ctrl+R)
- Check backend is still running
- Check proxy in Vite is working (`curl http://localhost:5173/api/v1/health`)

### "ChromaDB not initialized"

**Optional feature.** The system works without it:
```bash
# If you want RAG with ChromaDB:
pip install -e ".[rag]"
make ingest

# Otherwise: SecurityAgent uses hardcoded fallback knowledge
```

---

## Performance Baselines

On a typical machine:

| Stage | Time |
|-------|------|
| Fetch PR | ~2s |
| Security agent | ~8s |
| Bug detection | ~5s |
| Style agent | ~5s |
| Performance agent | ~4s |
| **Total** | **~30s** |

(4 agents run in parallel, so total = max(agent times) + overhead)

---

## Cleanup

```bash
# Stop backend
# Ctrl+C in backend terminal

# Stop dashboard
# Ctrl+C in dashboard terminal

# Stop Redis
docker compose down
```

---

## What's Tested

- ✅ Backend FastAPI app starts & routes work
- ✅ Dashboard UI renders
- ✅ PR analysis via API
- ✅ Real-time SSE updates
- ✅ Findings grouped by category
- ✅ LLM integration (security, bugs, style, performance)
- ✅ Git integration (commits via GitHub API)
- ✅ Rate limiting, auth, logging

## What's NOT Tested

- ❌ Production deployment (no HTTPS, no DB, no load balancing)
- ❌ Webhook signature validation (needs real GitHub server)
- ❌ Auto-fix commits (needs `contents:write` permission)
- ❌ Concurrent reviews (MVP in-process; prod would use Redis/ARQ)

---

## Next Steps

1. **Deploy**: Move to a real server with a database
2. **Scale**: Enqueue reviews to Redis/ARQ for background processing
3. **Enhance**: Add more agents, improve LLM prompts, add caching
4. **Monitor**: Add observability (Grafana, Sentry, etc.)
