#!/bin/bash
# Bring up the full local demo stack: infra + API + worker + dashboard + Streamlit.

set -euo pipefail
set -m

ROOT_DIR="/workspaces/multi-agent-code-review"
cd "$ROOT_DIR"

BACKEND_ONLY=false

show_usage() {
    cat <<'EOF'
Usage:
  ./run-demo.sh [--backend-only|-b]

Options:
  --backend-only, -b   Start only backend services (redis, chromadb, api, worker)
  --help, -h           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend-only|-b)
            BACKEND_ONLY=true
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
    shift
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

wait_for_http() {
    local name="$1"
    local url="$2"
    local attempts="${3:-60}"

    for ((i=1; i<=attempts; i++)); do
        if curl -sf "$url" >/dev/null 2>&1; then
            echo -e "${GREEN}✓ ${name} is up${NC}"
            return 0
        fi
        sleep 1
    done

    echo -e "${RED}✗ ${name} did not become ready (${url})${NC}"
    return 1
}

wait_for_process() {
    local name="$1"
    local pid="$2"

    if kill -0 "$pid" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ ${name} process running (pid=${pid})${NC}"
        return 0
    fi

    echo -e "${RED}✗ ${name} process exited early${NC}"
    return 1
}

cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping demo processes...${NC}"
    jobs -p | xargs -r kill 2>/dev/null || true
    echo -e "${YELLOW}Done. Docker services are still running (redis/chromadb).${NC}"
    echo -e "${YELLOW}Run 'make down' to stop Docker services.${NC}"
}

trap cleanup SIGINT SIGTERM EXIT

echo -e "${BLUE}Starting Cap PR Review demo stack...${NC}"
if [[ "$BACKEND_ONLY" == "true" ]]; then
    echo -e "${BLUE}Mode: backend-only${NC}"
else
    echo -e "${BLUE}Mode: full stack${NC}"
fi

if [[ ! -d ".venv" ]]; then
    echo -e "${RED}Missing .venv. Run: make install${NC}"
    exit 1
fi

if [[ "$BACKEND_ONLY" == "false" ]]; then
    if [[ ! -d "dashboard/node_modules" ]]; then
        echo -e "${YELLOW}Installing dashboard dependencies...${NC}"
        npm --prefix dashboard install
    fi

    if ! .venv/bin/python -m pip show streamlit >/dev/null 2>&1; then
        echo -e "${YELLOW}Installing Streamlit dependencies for eval_PR...${NC}"
        .venv/bin/pip install -r eval_PR/requirements.txt
    fi
fi

if [[ -f ".env" ]]; then
    set -a
    source .env
    set +a
else
    echo -e "${YELLOW}No .env file found. Running with defaults and current shell env.${NC}"
fi

export PYTHONPATH="$ROOT_DIR/eval_PR:${PYTHONPATH:-}"

echo -e "${GREEN}Starting Docker dependencies (redis + chromadb)...${NC}"
docker compose up -d redis
docker compose --profile chromadb up -d chromadb

echo -e "${GREEN}Starting backend API...${NC}"
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!


echo -e "${GREEN}Starting background worker...${NC}"
.venv/bin/python -m arq src.worker.WorkerSettings &
WORKER_PID=$!

DASHBOARD_PID=""
STREAMLIT_PID=""

if [[ "$BACKEND_ONLY" == "false" ]]; then
    echo -e "${GREEN}Starting dashboard...${NC}"
    npm --prefix dashboard run dev -- --host 0.0.0.0 &
    DASHBOARD_PID=$!

    echo -e "${GREEN}Starting Streamlit...${NC}"
    .venv/bin/python -m streamlit run eval_PR/eval_pr/gui/app.py --server.address 0.0.0.0 --server.port 8501 &
    STREAMLIT_PID=$!
fi

echo ""
echo -e "${BLUE}Running startup health checks...${NC}"

if ! docker exec cap-pr-review-redis redis-cli ping | grep -q "PONG"; then
    echo -e "${RED}✗ Redis health check failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Redis is healthy${NC}"

wait_for_http "ChromaDB" "http://localhost:8001/api/v2/heartbeat"
wait_for_process "Backend API" "$API_PID"
wait_for_process "ARQ worker" "$WORKER_PID"
wait_for_http "Backend API health" "http://localhost:8000/health"
wait_for_http "Backend API ready" "http://localhost:8000/ready"

if [[ "$BACKEND_ONLY" == "false" ]]; then
    wait_for_process "Dashboard" "$DASHBOARD_PID"
    wait_for_process "Streamlit" "$STREAMLIT_PID"
    wait_for_http "Dashboard" "http://localhost:5173"
    wait_for_http "Streamlit" "http://localhost:8501"
fi


echo ""
echo -e "${BLUE}Demo services are ready.${NC}"
echo -e "  API:        http://localhost:8000"
echo -e "  API Docs:   http://localhost:8000/docs"
if [[ "$BACKEND_ONLY" == "false" ]]; then
    echo -e "  Dashboard:  http://localhost:5173"
    echo -e "  Streamlit:  http://localhost:8501"
fi
echo ""
echo -e "Press Ctrl+C to stop local processes."

wait
