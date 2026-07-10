#!/bin/bash
# Combined script to run both backend and frontend with visible logs

set -m  # Enable job control

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Cap PR Review — Starting Backend + Frontend          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗ Virtual environment not found!${NC}"
    echo "  Run: python3.14 -m venv .venv"
    echo "       source .venv/bin/activate"
    echo "       pip install -e '.[dev]'"
    exit 1
fi

# Check if node_modules exists
if [ ! -d "dashboard/node_modules" ]; then
    echo -e "${YELLOW}! Installing dashboard dependencies...${NC}"
    cd dashboard
    npm install
    cd ..
fi

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    jobs -p | xargs -r kill 2>/dev/null || true
    echo -e "${YELLOW}✓ All services stopped${NC}"
    exit 0
}

# Set trap to catch Ctrl+C
trap cleanup SIGINT SIGTERM EXIT

echo -e "${GREEN}Starting Redis...${NC}"
docker compose up -d redis 2>/dev/null || true
sleep 2

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}BACKEND LOGS:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

sleep 3

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}FRONTEND LOGS:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
cd dashboard
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                   🚀 READY TO USE 🚀                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}Backend:${NC}  http://localhost:8000"
echo -e "  ${BLUE}API Docs:${NC} http://localhost:8000/docs"
echo -e "  ${BLUE}Frontend:${NC} http://localhost:5173"
echo ""
echo -e "  ${YELLOW}Shortcuts:${NC}"
echo -e "    Backend:  Press 'b' to focus backend logs"
echo -e "    Frontend: Press 'f' to focus frontend logs"
echo -e "    Both:     Press 'l' to show job list"
echo ""
echo -e "  ${RED}Stop:${NC} Press Ctrl+C to stop all services"
echo ""

# Wait for both processes to keep the script alive
wait
