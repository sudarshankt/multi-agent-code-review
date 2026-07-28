#!/bin/bash
# One-command startup for every service used in this repo:
# Redis, backend API, dashboard, eval_PR GUI, eval_harness GUI.

set -m  # Enable job control

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Cap PR Review — Starting All Systems                     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ ! -d ".venv" ]; then
    echo -e "${RED}✗ Virtual environment not found!${NC}"
    echo "  Run: python3.12 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
    exit 1
fi

if [ ! -d "dashboard/node_modules" ]; then
    echo -e "${YELLOW}! Installing dashboard dependencies...${NC}"
    (cd dashboard && npm install)
fi

if [ ! -f ".venv/bin/eval-pr-start" ]; then
    echo -e "${YELLOW}! Installing eval_PR package...${NC}"
    (cd eval_PR && ../.venv/bin/pip install -q -r requirements.txt && ../.venv/bin/pip install -q -e ".[gui]")
fi

cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    jobs -p | xargs -r kill 2>/dev/null || true
    echo -e "${YELLOW}✓ All services stopped (Redis container left running — 'make down' to stop it)${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

echo -e "${GREEN}Starting Redis...${NC}"
docker compose up -d redis 2>/dev/null || true
sleep 2

echo -e "${GREEN}Starting backend (uvicorn :8000)...${NC}"
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &

echo -e "${GREEN}Starting dashboard (vite :5173)...${NC}"
(cd dashboard && npm run dev) &

echo -e "${GREEN}Starting eval_PR GUI (streamlit :8501)...${NC}"
(cd eval_PR && ../.venv/bin/python -m streamlit run eval_pr/gui/app.py --server.address 0.0.0.0 --server.port 8501) &

echo -e "${GREEN}Starting eval_harness GUI (streamlit :8502)...${NC}"
(cd eval_harness/eval_harness && ../../.venv/bin/python -m streamlit run gui/app.py --server.address 0.0.0.0 --server.port 8502) &

sleep 3

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                   🚀 READY TO USE 🚀                       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}Backend API:${NC}       http://localhost:8000  (docs: /docs)"
echo -e "  ${BLUE}Dashboard:${NC}         http://localhost:5173"
echo -e "  ${BLUE}eval_PR GUI:${NC}       http://localhost:8501"
echo -e "  ${BLUE}eval_harness GUI:${NC}  http://localhost:8502"
echo ""
echo -e "  ${RED}Stop:${NC} Press Ctrl+C to stop all services (Redis container keeps running; 'make down' to stop it too)"
echo ""

wait
