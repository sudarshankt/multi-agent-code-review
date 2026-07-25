# Comprehensive Initialization & Verification Guide

## Overview

The **`init-setup.sh`** script provides a complete, automated initialization of the entire multi-agent code review system with comprehensive health checks, LLM verification, and environment validation.

## Quick Start

```bash
./init-setup.sh
```

This single command handles everything needed to get the system fully operational.

---

## What Gets Initialized (14 Phases)

### Phase 1: Prerequisite Verification
**What's checked:**
- ✅ Python 3 installed (version detected)
- ✅ Docker installed (version detected)
- ✅ Docker Compose available
- ✅ Node.js installed (optional, for dashboard)

**Why it matters:** Ensures your system has all required tools before proceeding.

---

### Phase 2: Python Virtual Environment Setup
**What's done:**
- ✅ Creates `.venv/` if it doesn't exist
- ✅ Activates the virtual environment
- ✅ Upgrades pip to latest version

**Why it matters:** Isolated Python environment prevents conflicts with system packages.

---

### Phase 3: Dependencies Installation
**What's installed:**
- ✅ **Core dependencies** (FastAPI, LangGraph, Pydantic, etc.)
- ✅ **Development tools** (pytest, ruff, honcho)
- ✅ **RAG dependencies** (chromadb, sentence-transformers)
- ✅ **Streamlit** for eval_PR app

**Why it matters:** All required libraries are available in correct versions.

---

### Phase 4: Environment Configuration
**What's configured:**
- ✅ `.env` file created from template (if missing)
- ✅ Loads environment variables
- ✅ Validates critical variables:
  - `LLM_API_KEY` (REQUIRED)
  - `GITHUB_TOKEN` (optional)
- ✅ Provides clear error messages if required vars are missing

**Why it matters:** System won't work without proper configuration.

---

### Phase 5: Dashboard Setup
**What's done:**
- ✅ Checks if `dashboard/node_modules/` exists
- ✅ Installs npm dependencies if needed
- ✅ Gracefully skips if npm unavailable

**Why it matters:** React dashboard requires Node.js dependencies.

---

### Phase 6: Docker Services Startup
**What's started:**
- ✅ **Redis** (`:6379`) - Task queue backend
- ✅ **ChromaDB** (`:8001`) - Vector database

**What's verified:**
- ✅ Redis responds to PING command
- ✅ ChromaDB heartbeat endpoint accessible

**Why it matters:** Foundation for all asynchronous operations and RAG.

---

### Phase 7: Knowledge Base Ingestion
**What's done:**
- ✅ Runs `scripts/ingest_owasp.py`
- ✅ Loads OWASP Top 10 2021 documents
- ✅ Loads CWE mappings
- ✅ Embeds documents with sentence-transformers

**What's verified:**
- ✅ Document count reported (16 documents by default)
- ✅ ChromaDB collection populated

**Why it matters:** Enables RAG-powered security analysis with real-world vulnerability knowledge.

---

### Phase 8: Backend Services Startup
**What's started:**
- ✅ **FastAPI Backend** (`:8000`) - Main API server
- ✅ **ARQ Worker** - Asynchronous job processor

**What's verified:**
- ✅ Both processes started successfully (PIDs recorded)
- ✅ No immediate crashes detected

**Why it matters:** Core API and background job processing.

---

### Phase 9: Backend API Health Checks
**What's checked:**
- ✅ `/health` endpoint responding (retries for 30 seconds)
- ✅ `/ready` endpoint showing "ready" status
- ✅ `/docs` (Swagger UI) accessible

**Why it matters:** Ensures API is fully initialized and ready to accept requests.

---

### Phase 10: LLM Service Verification
**What's verified:**
- ✅ LLM provider configured (Anthropic, DeepSeek, etc.)
- ✅ Model names loaded from settings
- ✅ API key configured
- ✅ LLMService class instantiates successfully

**What's reported:**
```
[INFO] LLM Provider: deepseek
[INFO] Primary Model: deepseek-v4-pro
[INFO] API Key configured: True
[SUCCESS] LLM service initialized successfully
```

**Why it matters:** Confirms LLM connectivity before accepting PR reviews.

---

### Phase 11: GitHub Service Verification
**What's verified:**
- ✅ GitHub API URL configured
- ✅ GitHub token status (required for actual PR access)
- ✅ GitHubService class instantiates successfully

**What's reported:**
```
[INFO] GitHub API: https://api.github.com
[INFO] GitHub Token configured: False  (or True if set)
[SUCCESS] GitHub service initialized successfully
```

**Why it matters:** Ensures system can authenticate with GitHub when needed.

---

### Phase 12: Infrastructure Verification
**What's verified:**
- ✅ **Redis** - Successfully connects and verifies functionality
- ✅ **ChromaDB** - Lists collections and document counts:
  ```
  [INFO] ChromaDB collections: 1
  [INFO]   - owasp_knowledge: 16 documents
  ```

**Why it matters:** Confirms persistent storage and vector database are operational.

---

### Phase 13: Agent Verification
**What's verified:**
- ✅ SecurityAgent importable and available
- ✅ BugDetectionAgent importable and available
- ✅ StyleAgent importable and available
- ✅ PerformanceAgent importable and available
- ✅ FixAgent importable and available

**Why it matters:** All analysis agents are properly initialized and ready.

---

### Phase 14: Frontend Services Startup (Optional)
**What's started:**
- ✅ **React Dashboard** (`:5173`) - if npm available
- ✅ **Streamlit App** (`:8501`) - eval_PR interface

**What's verified:**
- ✅ Processes started successfully
- ✅ Endpoints responding to HTTP requests (with timeout allowance)

**Why it matters:** Provides user interfaces for monitoring and evaluation.

---

## Final Summary Output

The script provides a comprehensive summary with:

```
═══════════════════════════════════════════════════════
✓ PASSED: XX
⚠ WARNINGS: XX
✗ FAILED: XX

Available Services:
  ✓ Backend API:     http://localhost:8000
  ✓ API Docs:        http://localhost:8000/docs
  ✓ Redis:           localhost:6379
  ✓ ChromaDB:        localhost:8001
  Dashboard:         http://localhost:5173
  Streamlit:         http://localhost:8501
```

---

## Environment Variables Verified

### Critical (MUST be set):
- `LLM_API_KEY` - Your LLM provider API key (Anthropic, DeepSeek, etc.)

### Important (Should be set):
- `GITHUB_TOKEN` - GitHub personal access token (for PR access)

### Infrastructure:
- `REDIS_HOST`, `REDIS_PORT` - Redis connection
- `CHROMADB_MODE`, `CHROMADB_HOST`, `CHROMADB_PORT` - ChromaDB settings

### LLM Configuration:
- `PRIMARY_MODEL` - Main LLM model
- `FALLBACK_MODEL` - Fallback LLM
- `LLM_BASE_URL` - Custom LLM endpoint (if not using public API)
- `MODEL_PROVIDER` - LLM provider (anthropic, deepseek, etc.)

### See `.env.example` for complete list

---

## What Happens If Something Fails?

The script:
1. **Reports the specific failure** with clear error messages
2. **Continues where possible** (marks as warning if non-critical)
3. **Stops on critical failures** (prerequisites, dependencies)
4. **Provides actionable remediation** in error messages

Example:
```
✗ LLM_API_KEY is not set (REQUIRED)
Error: Missing required environment variables. Edit .env and re-run.
```

---

## How to Run

### One-time complete initialization:
```bash
./init-setup.sh
```

### Stop services:
```bash
Ctrl+C
```

### Stop Docker infrastructure only:
```bash
make down
```

---

## Comparison: Manual vs Automated

### Manual Setup (Old Way):
```bash
make install                    # Install deps
cp .env.example .env           # Config
make up                         # Start Docker
.venv/bin/python scripts/ingest_owasp.py  # Ingest KB
make run-demo                   # Start services
# ... manual verification needed
```

### Automated Setup (New Way):
```bash
./init-setup.sh
# Everything done with comprehensive verification
```

---

## Troubleshooting

### Issue: "Python 3 not found"
**Solution:** Install Python 3.12 or later

### Issue: "Docker not found"
**Solution:** Install Docker

### Issue: "LLM_API_KEY is not set"
**Solution:** Edit `.env` and add your API key:
```bash
nano .env
# Set: LLM_API_KEY=your_key_here
./init-setup.sh
```

### Issue: "Failed to start ChromaDB"
**Solution:** Check Docker status and available disk space

### Issue: "Redis connection failed"
**Solution:** 
```bash
docker ps  # Check if redis is running
make down && make up  # Restart Docker services
```

---

## What's Next?

After `init-setup.sh` completes successfully:

1. **Explore the API:**
   - Visit http://localhost:8000/docs
   - Try the `/analyze` endpoint with a real PR URL

2. **Use the Dashboard:**
   - Visit http://localhost:5173
   - Enter a GitHub PR URL
   - Watch real-time analysis progress

3. **Try the Eval Tool:**
   - Visit http://localhost:8501
   - Upload PR data or test results
   - Generate evaluation reports

---

## Verification Checklist

After initialization, verify:
- [ ] Backend API responding: `curl http://localhost:8000/health`
- [ ] LLM service working: Check logs for "LLM service initialized"
- [ ] Knowledge base loaded: 16 OWASP documents in ChromaDB
- [ ] All agents available: Check "Agent verification" in output
- [ ] Redis working: Can connect and retrieve keys
- [ ] Dashboard running: Can access http://localhost:5173
- [ ] Streamlit running: Can access http://localhost:8501
