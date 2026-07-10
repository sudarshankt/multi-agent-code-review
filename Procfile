# Cap PR Review - Process definitions for honcho
# Usage: honcho start
# Or individual processes: honcho start backend, honcho start frontend

backend: .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
frontend: cd dashboard && npm run dev
