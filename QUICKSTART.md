# Quick Start — 5 Minutes to First Review

## Prerequisites

- ✅ Python 3.12+ installed (`make venv`/`make install` hardcode `python3.14`
  specifically — if you don't have that exact version, run
  `python3.12 -m venv .venv` yourself first, then `make install` to reuse it)
- ✅ Node.js 18+ installed
- ✅ Docker + Docker Compose installed (for Redis — `make up` only starts
  Redis; ChromaDB runs embedded by default, no container needed)
- ✅ An LLM API key — DeepSeek is the configured default in `.env.example`
  (`LLM_API_KEY`); Anthropic/OpenAI/Gemini also work if you switch
  `MODEL_PROVIDER`/`PRIMARY_MODEL` and set the matching key
- ✅ GitHub personal access token (PAT)

## ⚡ Quick: Run Everything Together

### Prerequisites (One Time)
```bash
# Initialize Redis & ChromaDB in background
make up
# ✓ Services ready. Keep them running, or stop later with: make down
```

### Run Backend + Frontend
```bash
make run-all
```

This uses **honcho** to manage both processes:
- **Backend** on http://localhost:8000 (API docs: `/docs`)
- **Frontend** on http://localhost:5173
- **All logs visible** in your terminal, prefixed with [backend] or [frontend]
- **Stop everything** with Ctrl+C

### Alternative: Single Services
```bash
make run-backend       # Backend only
make run-frontend      # Frontend only
```

### Alternative: Separate Terminals
```bash
# Terminal 1
make run

# Terminal 2
cd dashboard && npm run dev
```

## 1. Setup (One-Time)

```bash
# Install dependencies (uses python3.14 — see Prerequisites above if you
# don't have that version)
make install

# Configure environment
cp .env.example .env

# Edit .env and add your credentials — at minimum:
#   LLM_API_KEY=sk-xxxxx        (DeepSeek, the configured default provider)
#   GITHUB_TOKEN=github_pat_xxxxx
# (swap in ANTHROPIC_API_KEY/OPENAI_API_KEY instead if you change MODEL_PROVIDER)
```

## 2. Initialize Infrastructure

```bash
make up
# Starts Redis in background (ChromaDB is embedded, not a container —
# CHROMADB_MODE=embedded by default, no separate service to start)
# Keep it running while developing
```

## 3. Start Backend + Frontend

```bash
make run-all
# Manages both services with honcho
# All logs visible with [backend] and [frontend] prefixes
# Stop with Ctrl+C
```

## 4. Test It

1. Open http://localhost:5173 in your browser
2. Enter a GitHub PR URL:
   ```
   https://github.com/owner/repo/pull/123
   ```
   (Use any real PR, e.g., `https://github.com/facebook/react/pull/28836`)

3. Click **"Analyze PR"**

4. Watch the magic:
   - Status updates in real-time
   - Findings appear as they're discovered
   - Grouped by category (security, bugs, style, performance)

## ✨ What You're Seeing

**Real AI analysis:**
- **SecurityAgent**: Scans for OWASP top 10 (SQL injection, XSS, etc.)
- **BugDetectionAgent**: Python AST + LLM finds logic errors
- **StyleAgent**: Ruff linter + LLM for readability
- **PerformanceAgent**: Detects complexity, memory leaks, hotspots
- **FixAgent**: Auto-generates & commits fixes (if applicable)

All 4 agents run **in parallel** → typical review = 30–60 seconds.

## 5. Run the Test Suite

```bash
pytest -q   # or: make test
# 112 tests should pass. Tests live in tests_local/, not tests/.
```

## 📖 Learn More

- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** — Detailed setup + troubleshooting
- **[README.md](README.md)** — Architecture overview + API docs
- **[docs/USER_FLOWS.md](docs/USER_FLOWS.md)** — Integration examples
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** — What was built

## 🔍 RAG / Knowledge Base (Optional)

**ChromaDB is optional.** The system works without it but performs better with it:

- **Without ChromaDB**: Uses hardcoded OWASP security knowledge (fallback)
- **With ChromaDB**: Retrieves RAG vectors from full OWASP database

### Install RAG Support
```bash
# Option 1: Install all optional deps
pip install -e '.[rag]'

# Option 2: Just ChromaDB + embeddings
pip install chromadb sentence-transformers

# Option 3: Ingest OWASP docs (after install)
make ingest
```

If you see `chromadb_not_installed` in logs → RAG is skipped, security checks still work with fallback knowledge.

## 🐛 Troubleshooting

| Problem | Fix |
|---------|-----|
| "API key invalid" | Check `.env` — `LLM_API_KEY` (DeepSeek, default) or `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` if you changed `MODEL_PROVIDER` |
| "GitHub token invalid" | Check `.env` `GITHUB_TOKEN` scope |
| "PR not found" | Use a **real, public** PR URL |
| "SSE not updating" | Reload browser (Cmd+R / Ctrl+R) |
| `pytest` finds 0 tests or errors on unrelated files | `pyproject.toml`'s `testpaths` must be `tests_local`, not `tests` |
| Dashboard's "Run Tests" always says nothing to run | Expected if the reviewed PR's branch has no `tests_local/` directory — not a bug |
| 401 on create-review / apply-fixes via the API | `API_KEY` is set in `.env` — send it as the `X-API-Key` header (only relevant if you set this for a public deployment) |
| "Backend not running" | `curl http://localhost:8000/health` |
| "chromadb_not_installed" | Optional—falls back to hardcoded OWASP knowledge. Install with: `pip install -e '.[rag]'` |

## 📊 Performance

- **Typical review**: 30–60 seconds
- **Agents**: 4 running in parallel
- **Speed vs serial**: ~75% faster

## 🚀 Production

When ready to deploy:
1. Replace in-memory dict with PostgreSQL
2. Enable Redis/ARQ background queues
3. Add HTTPS + SSL cert
4. Configure monitoring
5. See [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md#deployment-checklist)

---

**Questions?** Check [TESTING_GUIDE.md](TESTING_GUIDE.md) or [docs/USER_FLOWS.md](docs/USER_FLOWS.md) for detailed walkthroughs.
