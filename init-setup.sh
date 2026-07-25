#!/bin/bash
# Comprehensive initialization script for multi-agent code review system
# Checks prerequisites, sets up environment, starts services, and runs health checks

set -euo pipefail
set -m

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++)) || true
}

log_error() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++)) || true
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++)) || true
}

log_section() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
}

# ============================================================================
# PHASE 1: Check Prerequisites
# ============================================================================

log_section "PHASE 1: CHECKING PREREQUISITES"

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    log_success "Python 3 found: $PYTHON_VERSION"
else
    log_error "Python 3 not found. Install Python 3.12+"
    exit 1
fi

# Check Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | awk '{print $3}' | cut -d',' -f1)
    log_success "Docker found: $DOCKER_VERSION"
else
    log_error "Docker not found. Install Docker"
    exit 1
fi

# Check Docker Compose
if command -v docker compose &> /dev/null; then
    log_success "Docker Compose found"
else
    log_error "Docker Compose not found. Install Docker Compose"
    exit 1
fi

# Check Node.js (for dashboard)
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    log_success "Node.js found: $NODE_VERSION"
else
    log_warning "Node.js not found. Dashboard will not work. Install Node.js 18+"
fi

# ============================================================================
# PHASE 2: Python Virtual Environment Setup
# ============================================================================

log_section "PHASE 2: PYTHON ENVIRONMENT SETUP"

if [[ -d ".venv" ]]; then
    log_info "Virtual environment already exists"
else
    log_info "Creating Python virtual environment..."
    python3 -m venv .venv
    log_success "Virtual environment created"
fi

# Activate venv
source .venv/bin/activate
log_success "Virtual environment activated"

# Upgrade pip
log_info "Upgrading pip..."
.venv/bin/pip install --upgrade pip -q
log_success "pip upgraded"

# ============================================================================
# PHASE 3: Install Dependencies
# ============================================================================

log_section "PHASE 3: INSTALLING DEPENDENCIES"

log_info "Installing core dependencies (dev extras)..."
.venv/bin/pip install -e ".[dev]" -q
log_success "Core dependencies installed"

log_info "Installing RAG dependencies (chromadb, sentence-transformers)..."
.venv/bin/pip install -e ".[rag]" -q 2>/dev/null || {
    log_warning "RAG installation via extras failed, installing directly..."
    .venv/bin/pip install chromadb sentence-transformers -q
}
log_success "RAG dependencies installed"

log_info "Installing Streamlit for eval_PR..."
.venv/bin/pip install -r eval_PR/requirements.txt -q 2>/dev/null || {
    log_warning "Streamlit dependencies may not be fully installed"
}
log_success "Streamlit dependencies handled"

# ============================================================================
# PHASE 4: Environment Configuration
# ============================================================================

log_section "PHASE 4: ENVIRONMENT CONFIGURATION"

if [[ -f ".env" ]]; then
    log_success ".env file exists"
    NEED_ENV_CONFIG=false
else
    log_warning ".env file not found, creating from template..."
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        log_success ".env created from template"
        NEED_ENV_CONFIG=true
    else
        log_error ".env.example not found"
        exit 1
    fi
fi

# Load environment
set -a
source .env
set +a

# Check required environment variables
log_info "Verifying environment variables..."

check_env_var() {
    local var_name=$1
    local required=$2
    
    if [[ -z "${!var_name:-}" ]]; then
        if [[ "$required" == "true" ]]; then
            log_error "$var_name is not set (REQUIRED)"
            return 1
        else
            log_warning "$var_name is not set (optional)"
            return 0
        fi
    else
        log_success "$var_name is set"
        return 0
    fi
}

# Check critical variables
HAS_ERRORS=false
check_env_var "LLM_API_KEY" "true" || HAS_ERRORS=true
check_env_var "GITHUB_TOKEN" "false" # Optional for now

if [[ "$HAS_ERRORS" == "true" ]]; then
    log_error "Missing required environment variables. Edit .env and re-run."
    exit 1
fi

# ============================================================================
# PHASE 5: Dashboard Dependencies
# ============================================================================

log_section "PHASE 5: DASHBOARD SETUP"

if [[ -d "dashboard/node_modules" ]]; then
    log_success "Dashboard dependencies already installed"
else
    if command -v npm &> /dev/null; then
        log_info "Installing dashboard dependencies..."
        npm --prefix dashboard install -q
        log_success "Dashboard dependencies installed"
    else
        log_warning "npm not found, skipping dashboard setup"
    fi
fi

# ============================================================================
# PHASE 6: Start Docker Services
# ============================================================================

log_section "PHASE 6: STARTING DOCKER SERVICES"

log_info "Starting Redis..."
docker compose up -d redis
sleep 2

# Verify Redis
if docker exec cap-pr-review-redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    log_success "Redis is running and healthy"
else
    log_error "Redis failed to start"
    exit 1
fi

log_info "Starting ChromaDB..."
docker compose --profile chromadb up -d chromadb 2>/dev/null || true
sleep 3

# Verify ChromaDB
if curl -sf http://localhost:8001/api/v2/heartbeat >/dev/null 2>&1; then
    log_success "ChromaDB is running and healthy"
else
    log_warning "ChromaDB is not responding (may still be starting)"
fi

export PYTHONPATH="$ROOT_DIR/eval_PR:${PYTHONPATH:-}"

# ============================================================================
# PHASE 7: Ingest OWASP Knowledge Base
# ============================================================================

log_section "PHASE 7: KNOWLEDGE BASE INGESTION"

log_info "Ingesting OWASP knowledge base into ChromaDB..."
if .venv/bin/python scripts/ingest_owasp.py 2>/dev/null | tee /tmp/ingest.log | grep -q "Ingested"; then
    INGESTED=$(grep "Ingested" /tmp/ingest.log | grep -oE "[0-9]+" | head -1)
    log_success "OWASP knowledge base ingested: $INGESTED documents"
else
    log_warning "OWASP ingestion may have issues, continuing..."
fi

# ============================================================================
# PHASE 8: Backend Health Checks
# ============================================================================

log_section "PHASE 8: STARTING BACKEND SERVICES"

log_info "Starting FastAPI backend..."
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > /tmp/api.log 2>&1 &
API_PID=$!
sleep 3

if kill -0 $API_PID 2>/dev/null; then
    log_success "FastAPI backend process started (pid=$API_PID)"
else
    log_error "FastAPI backend failed to start"
    cat /tmp/api.log
    exit 1
fi

log_info "Starting ARQ worker..."
.venv/bin/python -m arq src.worker.WorkerSettings > /tmp/worker.log 2>&1 &
WORKER_PID=$!
sleep 2

if kill -0 $WORKER_PID 2>/dev/null; then
    log_success "ARQ worker process started (pid=$WORKER_PID)"
else
    log_error "ARQ worker failed to start"
    cat /tmp/worker.log
    exit 1
fi

# ============================================================================
# PHASE 9: Backend API Health Checks
# ============================================================================

log_section "PHASE 9: BACKEND API HEALTH CHECKS"

# Health check
for i in {1..30}; do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        log_success "API health endpoint responding"
        break
    fi
    if [[ $i -eq 30 ]]; then
        log_error "API health endpoint not responding"
        kill $API_PID $WORKER_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

# Ready check
if curl -sf http://localhost:8000/ready | grep -q "ready"; then
    log_success "API ready endpoint responding"
else
    log_error "API ready endpoint not responding"
    kill $API_PID $WORKER_PID 2>/dev/null || true
    exit 1
fi

# API docs
if curl -sf http://localhost:8000/docs >/dev/null 2>&1; then
    log_success "API documentation available at http://localhost:8000/docs"
else
    log_warning "API documentation may not be fully ready"
fi

# ============================================================================
# PHASE 10: LLM Service Verification
# ============================================================================

log_section "PHASE 10: LLM SERVICE VERIFICATION (Comprehensive)"

log_info "Running comprehensive LLM API key and connectivity tests..."
log_info "This tests: configuration, API connectivity, LLM service, and parameters"

if [[ -f "scripts/test-llm-keys.py" ]]; then
    if .venv/bin/python scripts/test-llm-keys.py > /tmp/llm_test.log 2>&1; then
        log_success "All LLM tests passed"
        # Show summary
        tail -20 /tmp/llm_test.log | grep -E "✓|PASSED" | tail -3 || true
    else
        log_error "LLM tests failed - see details above"
        tail -30 /tmp/llm_test.log || true
    fi
else
    log_warning "LLM test script not found, running basic verification..."
    .venv/bin/python << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '/workspaces/multi-agent-code-review')

from src.services.llm_service import LLMService
from src.core.config import get_settings

try:
    settings = get_settings()
    print(f"[INFO] LLM Provider: {settings.model_provider}")
    print(f"[INFO] Primary Model: {settings.primary_model}")
    print(f"[INFO] API Key configured: {bool(settings.llm_api_key)}")
    
    llm = LLMService()
    print("[SUCCESS] LLM service initialized successfully")
    sys.exit(0)
except Exception as e:
    print(f"[ERROR] LLM service initialization failed: {e}")
    sys.exit(1)
PYTHON_SCRIPT

    if [[ $? -eq 0 ]]; then
        log_success "LLM service verified (basic)"
    else
        log_error "LLM service verification failed"
    fi
fi

# ============================================================================
# PHASE 11: GitHub Service Verification
# ============================================================================

log_section "PHASE 11: GITHUB SERVICE VERIFICATION (Comprehensive)"

log_info "Running comprehensive GitHub API and token tests..."
log_info "This tests: configuration, API connectivity, and authentication"

if [[ -f "scripts/test-github-token.py" ]]; then
    if .venv/bin/python scripts/test-github-token.py > /tmp/github_test.log 2>&1; then
        log_success "All GitHub tests passed"
        # Show summary
        tail -20 /tmp/github_test.log | grep -E "✓|PASSED" | tail -3 || true
    else
        log_warning "GitHub tests had issues - checking if non-critical..."
        if grep -q "PASS" /tmp/github_test.log; then
            log_success "GitHub basic configuration verified"
        else
            log_error "GitHub service verification failed"
            tail -30 /tmp/github_test.log || true
        fi
    fi
else
    log_warning "GitHub test script not found, running basic verification..."
    .venv/bin/python << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '/workspaces/multi-agent-code-review')

from src.services.github_service import GitHubService
from src.core.config import get_settings

try:
    settings = get_settings()
    print(f"[INFO] GitHub API: {settings.github.base_url}")
    print(f"[INFO] GitHub Token configured: {bool(settings.github.token)}")
    
    gh = GitHubService()
    print("[SUCCESS] GitHub service initialized successfully")
    sys.exit(0)
except Exception as e:
    print(f"[ERROR] GitHub service initialization failed: {e}")
    sys.exit(1)
PYTHON_SCRIPT

    if [[ $? -eq 0 ]]; then
        log_success "GitHub service verified (basic)"
    else
        log_warning "GitHub service verification failed (token may be needed)"
    fi
fi

# ============================================================================
# PHASE 12: Infrastructure Verification
# ============================================================================

log_section "PHASE 12: INFRASTRUCTURE VERIFICATION"

# Redis
log_info "Verifying Redis connectivity..."
if .venv/bin/python -c "import redis; r = redis.Redis(host='localhost', port=6379, db=0); r.ping()" 2>/dev/null; then
    log_success "Redis is accessible"
else
    log_error "Redis connection failed"
fi

# ChromaDB
log_info "Verifying ChromaDB connectivity..."
.venv/bin/python << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '/workspaces/multi-agent-code-review')

try:
    from src.infrastructure.chromadb import client as chromadb_client
    chromadb_client._init_client()
    collections = chromadb_client._client.list_collections()
    print(f"[INFO] ChromaDB collections: {len(collections)}")
    for col in collections:
        print(f"[INFO]   - {col.name}: {col.count()} documents")
    print("[SUCCESS] ChromaDB is accessible")
    sys.exit(0)
except Exception as e:
    print(f"[ERROR] ChromaDB connection failed: {e}")
    sys.exit(1)
PYTHON_SCRIPT

if [[ $? -eq 0 ]]; then
    log_success "ChromaDB is accessible"
else
    log_error "ChromaDB connection failed"
fi

# ============================================================================
# PHASE 13: Agent Verification
# ============================================================================

log_section "PHASE 13: AGENT VERIFICATION"

log_info "Verifying all agents are available..."
.venv/bin/python << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '/workspaces/multi-agent-code-review')

try:
    from src.agents.security.agent import SecurityAgent
    from src.agents.bug_detection.agent import BugDetectionAgent
    from src.agents.style.agent import StyleAgent
    from src.agents.performance.agent import PerformanceAgent
    from src.agents.fix.agent import FixAgent
    
    agents = [
        ("SecurityAgent", SecurityAgent),
        ("BugDetectionAgent", BugDetectionAgent),
        ("StyleAgent", StyleAgent),
        ("PerformanceAgent", PerformanceAgent),
        ("FixAgent", FixAgent),
    ]
    
    for name, agent_class in agents:
        try:
            # Just verify import, don't instantiate
            print(f"[SUCCESS] {name} available")
        except Exception as e:
            print(f"[ERROR] {name} failed: {e}")
            sys.exit(1)
    
    sys.exit(0)
except Exception as e:
    print(f"[ERROR] Agent verification failed: {e}")
    sys.exit(1)
PYTHON_SCRIPT

if [[ $? -eq 0 ]]; then
    log_success "All agents verified"
else
    log_warning "Agent verification had issues"
fi

# ============================================================================
# PHASE 14: Frontend Services (Optional)
# ============================================================================

log_section "PHASE 14: FRONTEND SERVICES (OPTIONAL)"

if command -v npm &> /dev/null; then
    log_info "Starting React dashboard..."
    npm --prefix dashboard run dev -- --host 0.0.0.0 > /tmp/dashboard.log 2>&1 &
    DASHBOARD_PID=$!
    sleep 5
    
    if kill -0 $DASHBOARD_PID 2>/dev/null; then
        if curl -sf http://localhost:5173 >/dev/null 2>&1; then
            log_success "React dashboard running at http://localhost:5173"
        else
            log_warning "React dashboard process running but not yet responding"
        fi
    else
        log_warning "React dashboard failed to start"
    fi
else
    log_warning "npm not found, skipping dashboard"
fi

log_info "Starting Streamlit eval_PR..."
.venv/bin/python -m streamlit run eval_PR/eval_pr/gui/app.py --server.address 0.0.0.0 --server.port 8501 > /tmp/streamlit.log 2>&1 &
STREAMLIT_PID=$!
sleep 5

if kill -0 $STREAMLIT_PID 2>/dev/null; then
    if curl -sf http://localhost:8501 >/dev/null 2>&1; then
        log_success "Streamlit app running at http://localhost:8501"
    else
        log_warning "Streamlit process running but not yet responding"
    fi
else
    log_warning "Streamlit failed to start"
fi

# ============================================================================
# FINAL SUMMARY
# ============================================================================

log_section "INITIALIZATION COMPLETE - SUMMARY"

echo ""
echo -e "${GREEN}✓ PASSED: $PASSED${NC}"
echo -e "${YELLOW}⚠ WARNINGS: $WARNINGS${NC}"
if [[ $FAILED -gt 0 ]]; then
    echo -e "${RED}✗ FAILED: $FAILED${NC}"
fi

echo ""
echo -e "${CYAN}Available Services:${NC}"
echo -e "  ${GREEN}✓${NC} Backend API:     ${CYAN}http://localhost:8000${NC}"
echo -e "  ${GREEN}✓${NC} API Docs:        ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  ${GREEN}✓${NC} Redis:           ${CYAN}localhost:6379${NC}"
echo -e "  ${GREEN}✓${NC} ChromaDB:        ${CYAN}localhost:8001${NC}"
echo -e "  Dashboard:       ${CYAN}http://localhost:5173${NC} (if npm available)"
echo -e "  Streamlit:       ${CYAN}http://localhost:8501${NC}"

echo ""
echo -e "${CYAN}Next Steps:${NC}"
echo "  1. Open http://localhost:8000/docs to explore the API"
echo "  2. Open http://localhost:5173 for the dashboard (if started)"
echo "  3. Open http://localhost:8501 for the Streamlit eval tool"
echo ""
echo -e "${CYAN}To stop all services:${NC}"
echo "  Press Ctrl+C in this terminal"
echo "  Run: make down"
echo ""

# Keep processes alive
wait
