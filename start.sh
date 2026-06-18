#!/bin/bash

# Terminate background processes on exit
trap "kill 0" EXIT

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}    Starting Fernandes Unified Automation Hub    ${NC}"
echo -e "${GREEN}=================================================${NC}"

# Check if frontend needs to be built
if [ ! -d "frontend/dist" ]; then
    echo -e "${CYAN}Building Frontend production assets...${NC}"
    cd frontend && npm run build && cd ..
fi

echo -e "${CYAN}Starting Python FastAPI Backend + Frontend on http://localhost:8000...${NC}"
cd backend
if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment activation script not found!"
    exit 1
fi

echo -e "${GREEN}Fernandes is live at: http://localhost:8000${NC}"
echo -e "${CYAN}Agent MCP connection string: http://localhost:8000/mcp/sse${NC}"
echo -e "${CYAN}To run frontend development server (with hot-reloading): cd frontend && npm run dev${NC}"
echo -e "Press Ctrl+C to stop."

uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='*'
