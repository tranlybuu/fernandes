.PHONY: install start dev start-backend start-frontend clean

OS := $(shell uname -s)
VENV_DIR = backend/venv
VENV_ACTIVATE = $(VENV_DIR)/bin/activate
VENV_PIP = $(VENV_DIR)/bin/pip
VENV_PYTHON = $(VENV_DIR)/bin/python

install:
	@echo "=== Setting up Python Virtual Environment ==="
	python3 -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PIP) install -r backend/requirements.txt
	@echo "=== Installing Frontend Dependencies ==="
	cd frontend && npm install
	@echo "=== Setup Complete! Run 'make start' to run the application ==="

start-backend:
	@echo "=== Starting FastAPI Backend on port 8000 ==="
	cd backend && ../$(VENV_DIR)/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='*'

start-frontend:
	@echo "=== Starting Vite React Frontend on http://localhost:5173 ==="
	cd frontend && npm run dev

start:
	@echo "=== Building Frontend Production Assets ==="
	cd frontend && npm run build
	@echo "=== Starting Fernandes Unified Server on http://localhost:8000 ==="
	cd backend && ../$(VENV_DIR)/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='*'

dev:
	@echo "=== Starting Fernandes in Development Mode ==="
	@trap 'kill 0' EXIT; \
	make start-backend & \
	make start-frontend & \
	wait

clean:
	@echo "=== Cleaning up Caches and Dependencies ==="
	rm -rf frontend/node_modules frontend/dist
	rm -rf backend/venv
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
