#!/bin/bash

# Terminate background processes on exit
trap "kill 0" EXIT

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN}    Starting Fernandes Mobile Automation Hub   ${NC}"
echo -e "${GREEN}===============================================${NC}"

echo -e "${CYAN}Starting Python FastAPI Backend on http://localhost:8000...${NC}"
cd backend
if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment activation script not found!"
    exit 1
fi
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

echo -e "${CYAN}Starting Vite React Frontend on http://localhost:5173...${NC}"
cd ../frontend
npm run dev &
FRONTEND_PID=$!

# Wait for processes
wait
