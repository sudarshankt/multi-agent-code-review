#!/bin/bash
# Debug-friendly version using tmux for clean log separation

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Cap PR Review — Debug Mode (with separate log panes)    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo -e "${YELLOW}tmux not found. Falling back to simple mode...${NC}"
    exec ./run.sh
fi

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗ Virtual environment not found!${NC}"
    echo "  Run: python3.14 -m venv .venv && pip install -e '.[dev]'"
    exit 1
fi

# Kill any existing tmux session
tmux kill-session -t cap-pr-review 2>/dev/null || true

echo -e "${GREEN}Starting Redis...${NC}"
docker compose up -d redis 2>/dev/null || true
sleep 2

# Create new tmux session with 2 panes
echo -e "${GREEN}Creating tmux session with separate panes...${NC}"
tmux new-session -d -s cap-pr-review -x 240 -y 60

# Left pane: Backend (70% width)
tmux send-keys -t cap-pr-review "echo 'BACKEND LOGS:'; sleep 1; .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload" Enter

# Split into right pane (30% width)
sleep 2
tmux split-window -t cap-pr-review -h -p 30

# Right pane: Frontend
tmux send-keys -t cap-pr-review "echo 'FRONTEND LOGS:'; sleep 1; cd dashboard && npm run dev" Enter

# Sync panes so both scroll together
tmux set-window-option -t cap-pr-review synchronize-panes off

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                   🚀 READY TO USE 🚀                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}Backend:${NC}  http://localhost:8000"
echo -e "  ${BLUE}API Docs:${NC} http://localhost:8000/docs"
echo -e "  ${BLUE}Frontend:${NC} http://localhost:5173"
echo ""
echo -e "  ${YELLOW}Tmux Commands:${NC}"
echo -e "    Attach:    tmux attach -t cap-pr-review"
echo -e "    Left pane: Ctrl+B → Left Arrow"
echo -e "    Right pane: Ctrl+B → Right Arrow"
echo -e "    Detach:    Ctrl+B → D"
echo ""
echo -e "  ${RED}Stop:${NC} Ctrl+B → :kill-session"
echo ""

# Attach to the session
tmux attach -t cap-pr-review
