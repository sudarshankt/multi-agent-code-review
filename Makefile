# Use the venv interpreter explicitly (macOS only ships python3)
PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv install install-rag up down run run-all run-backend run-frontend run-debug run-sep worker test lint fmt ingest clean

venv:
	python3.14 -m venv .venv

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install-rag:
	$(PIP) install -e ".[rag]"

up:
	@echo "Starting Redis and ChromaDB..."
	docker compose up -d redis
	@echo "✓ Services initialized (detached)"
	@echo ""
	@echo "To stop them, run: make down"

down:
	docker compose down

run:
	$(PY) -m uvicorn src.main:app --host 0.0.0.0 --port 8000

run-all:
	@echo "Starting Redis and ChromaDB (background)..."
	@docker compose up -d redis 2>/dev/null || true
	@sleep 2
	@echo ""
	@echo "Starting Backend + Frontend with honcho..."
	@echo ""
	.venv/bin/honcho start

run-backend:
	@echo "Starting Backend only..."
	.venv/bin/honcho start backend

run-frontend:
	@echo "Starting Frontend only..."
	.venv/bin/honcho start frontend

run-sep:
	@echo "Terminal 1 (Backend):"
	@echo "  $(PY) -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload"
	@echo ""
	@echo "Terminal 2 (Frontend):"
	@echo "  cd dashboard && npm run dev"

worker:
	.venv/bin/arq src.worker.WorkerSettings

test:
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check src tests

fmt:
	.venv/bin/ruff format src tests

ingest:
	$(PY) scripts/ingest_owasp.py

clean:
	rm -rf .chroma __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
